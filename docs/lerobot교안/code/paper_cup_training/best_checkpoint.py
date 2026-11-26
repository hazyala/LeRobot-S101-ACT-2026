"""검증 손실이 가장 낮은 ACT 체크포인트를 best_model에 저장."""
import ast
import csv
import inspect
import json
import math
import os
from pathlib import Path
import shutil
import textwrap

from PIL import Image, ImageDraw, ImageFont


class BestCheckpoint:
    def __init__(self, output, records):
        self.output = Path(output)
        self.records = Path(records)
        self.losses = {}
        best_record = self.records / "best.json"
        self.best_loss = json.loads(best_record.read_text(encoding="utf-8"))["eval_loss"] if best_record.exists() else math.inf

    def log(self, step, kind, loss):
        path = self.records / "training_log.csv"
        new_file = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["step", "type", "loss"])
            writer.writerow([int(step), kind, float(loss)])

    def evaluation(self, step, loss):
        self.losses[int(step)] = float(loss)
        self.log(step, "validation", loss)

    def save_loss_graph(self):
        with (self.records / "training_log.csv").open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        series = {}
        for kind in ("train", "validation"):
            series[kind] = [(int(row["step"]), float(row["loss"])) for row in rows
                            if row["type"] == kind and math.isfinite(float(row["loss"]))]
        points = series["train"] + series["validation"]
        if not points:
            return

        image = Image.new("RGB", (1440, 900), "white")
        draw = ImageDraw.Draw(image)
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
        font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default()
        title_font = ImageFont.truetype(str(font_path), 32) if font_path.exists() else font
        left, top, right, bottom = 150, 140, 1370, 760
        x_max = max(x for x, _ in points)
        y_max = max(y for _, y in points)
        x_max = max(x_max, 1)
        y_max = max(y_max * 1.05, 0.001)

        draw.text((left, 45), "Training and validation loss", font=title_font, fill="#172033")
        for i in range(6):
            y = bottom - i * (bottom - top) / 5
            x = left + i * (right - left) / 5
            draw.line((left, y, right, y), fill="#dfe5ed", width=1)
            draw.line((x, top, x, bottom), fill="#edf1f5", width=1)
            draw.text((left - 18, y), f"{y_max * i / 5:.2f}", font=font,
                      fill="#526071", anchor="rm")
            draw.text((x, bottom + 14), f"{x_max * i / 5:,.0f}", font=font,
                      fill="#526071", anchor="mt")
        draw.line((left, top, left, bottom, right, bottom), fill="#536273", width=2)
        draw.text(((left + right) / 2, 840), "Training step", font=font, fill="#344255", anchor="mm")
        draw.text((25, top - 35), "Loss", font=font, fill="#344255")

        for kind, label, color, y_legend in (
            ("train", "Train (L1 + KL)", "#1f77b4", 78),
            ("validation", "Validation (L1)", "#ffb000", 112),
        ):
            pixels = [(left + x / x_max * (right - left), bottom - y / y_max * (bottom - top))
                      for x, y in series[kind]]
            if len(pixels) > 1:
                draw.line(pixels, fill=color, width=4, joint="curve")
            for x, y in pixels:
                draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)
            draw.line((950, y_legend, 1000, y_legend), fill=color, width=5)
            draw.text((1015, y_legend), label, font=font, fill="#344255", anchor="lm")

        pending = self.records / "loss.tmp.png"
        image.save(pending)
        os.replace(pending, self.records / "loss.png")

    def saved(self, step, checkpoint):
        loss = self.losses.pop(int(step), None)
        if loss is None:
            raise RuntimeError(f"{step}단계 검증 결과를 찾을 수 없습니다.")
        try:
            self.save_loss_graph()
        except (OSError, ValueError, KeyError) as error:
            print(f"손실 그래프 저장 실패: {error}", flush=True)
        if not math.isfinite(loss) or loss >= self.best_loss:
            return
        source = Path(checkpoint) / "pretrained_model"
        if not (source / "model.safetensors").is_file():
            raise RuntimeError("저장된 모델 파일을 찾을 수 없습니다.")

        # 기존 모델을 보존한 채 새 모델 복사 후 교체
        best = self.output / "best_model"
        staged = self.output / ".best_model_new"
        previous = self.output / ".best_model_previous"
        if staged.exists() or previous.exists():
            raise RuntimeError("이전 best 모델 교체가 완료되지 않았습니다. 결과 폴더를 확인해 주세요.")
        shutil.copytree(source, staged)
        if best.exists():
            best.rename(previous)
        try:
            staged.rename(best)
        except OSError:
            if previous.exists():
                previous.rename(best)
            raise
        if previous.exists():
            shutil.rmtree(previous)

        record = {"step": int(step), "eval_loss": loss,
                  "checkpoint": str(Path(checkpoint).relative_to(self.output)),
                  "model": str(best), "criterion": "lowest validation loss"}
        pending = self.records / "best.json.tmp"
        pending.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, self.records / "best.json")
        self.best_loss = loss
        print(f"최고 모델 갱신 · step {step} · 검증 손실 {loss:.6f}", flush=True)


def train_with_best(trainer, config, dataset_factory, records):
    if config.save_freq != config.eval_steps or config.steps % config.save_freq:
        raise ValueError("학습 단계는 저장·검증 주기의 배수여야 합니다.")
    tracker = BestCheckpoint(config.output_dir, records)
    original = inspect.unwrap(trainer.train)
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    function = tree.body[0]
    function.decorator_list = []

    class AddValidationCallback(ast.NodeTransformer):
        count = 0
        train_count = 0

        def visit_Expr(self, node):
            self.generic_visit(node)
            call = node.value
            if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name) and call.func.value.id == "logging"
                    and call.func.attr == "info" and len(call.args) == 1
                    and isinstance(call.args[0], ast.Name) and call.args[0].id == "train_tracker"):
                self.train_count += 1
                callback = ast.parse("_best.log(step, 'train', train_tracker.to_dict()['loss'])").body[0]
                return [node, ast.copy_location(callback, node)]
            return node
        def visit_Assign(self, node):
            self.generic_visit(node)
            value = node.value
            if (any(isinstance(t, ast.Name) and t.id == "eval_loss" for t in node.targets)
                    and isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr == "item" and isinstance(value.func.value, ast.Call)
                    and isinstance(value.func.value.func, ast.Attribute)
                    and value.func.value.func.attr == "reduce"):
                self.count += 1
                return [node, ast.copy_location(ast.parse("_best.evaluation(step, eval_loss)").body[0], node)]
            return node

    hook = AddValidationCallback()
    tree = hook.visit(tree)
    if hook.count != 1 or hook.train_count != 1:
        raise RuntimeError("설치된 LeRobot의 검증 코드가 달라 best 모델 연결을 확인해야 합니다.")
    ast.fix_missing_locations(tree)
    original_save = trainer.save_checkpoint

    def save_and_select(*args, **kwargs):
        result = original_save(*args, **kwargs)
        tracker.saved(kwargs["step"], kwargs["checkpoint_dir"])
        return result

    def save_last_pointer(checkpoint):
        # Windows에서 관리자 권한이나 심볼릭 링크 없이 최근 체크포인트 기록
        path = Path(checkpoint)
        (Path(records) / "last_checkpoint.txt").write_text(
            str(path.relative_to(config.output_dir)), encoding="utf-8")

    namespace = {**original.__globals__, "_best": tracker,
                 "save_checkpoint": save_and_select,
                 "update_last_checkpoint": save_last_pointer,
                 "make_train_eval_datasets": dataset_factory}
    exec(compile(tree, inspect.getfile(original), "exec"), namespace)
    return namespace[function.name](config)
