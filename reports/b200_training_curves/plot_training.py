from pathlib import Path
import re
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parent
font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams.update({'font.family':font_manager.FontProperties(fname='C:/Windows/Fonts/malgun.ttf').get_name(),'axes.unicode_minus':False,'font.size':11})
for n, label in [(1, 'Sorting 1 (단독)'), (2, 'Sorting 2 (혼합)')]:
    log = (ROOT / f'sorting{n}_training.log').read_text(encoding='utf-8', errors='replace')
    train = re.findall(r'step:([^\s]+)[^\r\n]*?\bloss:([\d.]+)', log)
    val = re.findall(r'step (\d+): eval_loss=([\d.]+)', log)
    if len(train) != 500 or len(val) != 25:
        raise ValueError(f'Unexpected log entries: {len(train)}, {len(val)}')
    xs = list(range(100, 50001, 100))
    ys = [float(v) for _,v in train]
    vx = [int(s) for s,_ in val]
    vy = [float(v) for _,v in val]
    assert vx == list(range(2000,50001,2000))
    fig, (a,b) = plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    a.plot(xs, ys, color='#2864ad', lw=1.6)
    a.set_yscale('log')
    a.yaxis.set_major_formatter(FuncFormatter(lambda value, pos: f'{value:g}'))
    a.set(title='학습 손실',xlabel='학습 스텝',ylabel='Training loss (로그 눈금)')
    b.plot(vx,vy,marker='o',markersize=3.2,color='#24907d',lw=1.7)
    best=vy.index(min(vy)); b.scatter([vx[best]],[vy[best]],color='#d94d3f',s=45,zorder=3)
    b.annotate(f'최저: {vx[best]:,}스텝\n{vy[best]:.4f}',(vx[best],vy[best]),xytext=(21000,max(vy)*.83),arrowprops={'arrowstyle':'->','color':'#d94d3f'},fontsize=10)
    b.set(title='검증 손실',xlabel='학습 스텝',ylabel='Validation loss')
    for ax in (a,b):
        ax.grid(alpha=.2); ax.spines[['top','right']].set_visible(False)
    fig.suptitle(f'{label} ACT 학습 및 검증 손실',fontsize=15,fontweight='bold')
    fig.savefig(ROOT / f'sorting{n}_loss.png',dpi=200,facecolor='white')
    print(f'Sorting {n}: {len(train)} train, {len(val)} validation; minimum {vx[best]} = {vy[best]}')

