"""Select the lowest finite validation loss without modifying installed LeRobot files."""
import ast
import inspect
import json
import logging
import math
import os
import textwrap
from pathlib import Path


class BestCheckpoint:
    def __init__(self, output):
        self.output = Path(output)
        self.losses = {}
        self.best_loss = math.inf

    def evaluation(self, step, loss):
        # Receive the full-precision reduced loss, rather than rounded log text.
        self.losses[int(step)] = float(loss)

    def saved(self, step, checkpoint):
        loss = self.losses.pop(int(step), None)
        if loss is None:
            raise RuntimeError(f'Checkpoint {step} has no matching validation result')
        if not math.isfinite(loss) or loss >= self.best_loss:
            return
        checkpoint = Path(checkpoint)
        if not (checkpoint / 'pretrained_model/model.safetensors').is_file():
            raise RuntimeError('Best checkpoint model is missing')
        # All numbered checkpoints are retained. Atomically update only the pointer.
        link = checkpoint.parent / 'best'
        temporary = checkpoint.parent / '.best.pending'
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(checkpoint.name, target_is_directory=True)
        os.replace(temporary, link)
        record = {'step': int(step), 'eval_loss': loss,
                  'checkpoint': str(checkpoint.relative_to(self.output)),
                  'criterion': 'lowest finite validation loss across saved checkpoints'}
        metadata = self.output / 'best.json'
        pending = metadata.with_suffix('.json.tmp')
        pending.write_text(json.dumps(record, indent=2) + '\n')
        os.replace(pending, metadata)
        self.best_loss = loss
        logging.info('Best checkpoint: step %s, eval_loss %.8f', step, loss)


def train_with_best(trainer, config):
    if config.save_freq != config.eval_steps or config.steps % config.save_freq:
        raise ValueError('Best selection requires matching evaluation/save intervals and final step')
    tracker = BestCheckpoint(config.output_dir)
    original = inspect.unwrap(trainer.train)
    tree = ast.parse(textwrap.dedent(inspect.getsource(original)))
    function = tree.body[0]
    function.decorator_list = []

    class AddEvaluationCallback(ast.NodeTransformer):
        count = 0

        def visit_Assign(self, node):
            # Hook precisely after distributed evaluation reduction, not batch losses.
            self.generic_visit(node)
            value = node.value
            if (any(isinstance(t, ast.Name) and t.id == 'eval_loss' for t in node.targets)
                    and isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                    and value.func.attr == 'item' and isinstance(value.func.value, ast.Call)
                    and isinstance(value.func.value.func, ast.Attribute)
                    and value.func.value.func.attr == 'reduce'):
                self.count += 1
                callback = ast.parse('_cup_best.evaluation(step, eval_loss)').body[0]
                return [node, ast.copy_location(callback, node)]
            return node

    hook = AddEvaluationCallback()
    tree = hook.visit(tree)
    if hook.count != 1:
        raise RuntimeError('LeRobot validation implementation changed; best hook needs review')
    ast.fix_missing_locations(tree)
    original_save = trainer.save_checkpoint

    def save_and_select(*args, **kwargs):
        result = original_save(*args, **kwargs)
        tracker.saved(kwargs['step'], kwargs['checkpoint_dir'])
        return result

    # Scoped copy of official function globals. Training, evaluation and saving stay official.
    # Neither the installed module nor its files are patched by this hook.
    namespace = {**original.__globals__, '_cup_best': tracker,
                 'save_checkpoint': save_and_select,
                 'make_train_eval_datasets': trainer.make_train_eval_datasets}
    exec(compile(tree, inspect.getfile(original), 'exec'), namespace)
    return namespace[function.name](config)
