"""Create a technical four-view comparison PNG with FFmpeg, without editing sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO=Path(__file__).resolve().parents[2]
VIEWS=(('front','FRONT'),('three_quarter','THREE-QUARTER'),('profile','PROFILE'),('back','BACK'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--renders',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    target=args.output.resolve()
    if target.exists() or target.with_suffix('.json').exists() or not (target.is_relative_to(REPO/'.local-assets') or target.is_relative_to(REPO/'output')):
        raise RuntimeError('Choose a new ignored PNG path')
    target.parent.mkdir(parents=True,exist_ok=True)
    cfg=json.loads(Path(__file__).with_name('uki_character.json').read_text())
    paths=[];provenance=[];labels=[]
    for row in ('REFERENCE V7','MODEL V4'):
        for view,label in VIEWS:
            p=(REPO/'.local-assets/characters/uki/references/views_v7'/f'uki_{view}_v7.png'
               if row=='REFERENCE V7' else args.renders/f'{view}.png')
            p=p.resolve()
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            if row=='REFERENCE V7':
                assert digest==cfg['references'][p.relative_to(REPO/'.local-assets').as_posix()]
            paths.append(p)
            labels.append(row+' - '+label)
            provenance.append({'file':p.relative_to(REPO).as_posix(),'sha256':digest})
    command=['ffmpeg','-v','error']
    for p in paths:
        command += ['-i',str(p)]
    filters=[]
    for i,label in enumerate(labels):
        prepare='crop=440:560:100:40,' if i>=4 else ''
        filters += [f'color=c=0xeeeae2:s=440x600:r=1[bg{i}]',
                    f'[{i}:v]{prepare}format=rgba[fg{i}]',
                    f"[bg{i}][fg{i}]overlay=0:40:shortest=1,drawtext=font='DejaVu Sans':text='{label}':fontsize=17:fontcolor=0x243044:x=14:y=12[p{i}]"]
    layout='|'.join(f'{(i%4)*440}_{(i//4)*600}' for i in range(8))
    filters.append(''.join(f'[p{i}]' for i in range(8))+f'xstack=inputs=8:layout={layout},format=rgb24[out]')
    command += ['-filter_complex',';'.join(filters),'-map','[out]','-frames:v','1','-threads','1',str(target)]
    subprocess.run(command,check=True,stdout=subprocess.DEVNULL)
    report={'purpose':'Geometric four-view comparison, not a replacement source or color proof',
            'order':[x[0] for x in VIEWS],'reference_transforms':'None; original 440x560 pixels composited on a light preview background',
            'render_transforms':'Crop only 100px left / 40px top from 640x640 to 440x560; no scaling or mirroring',
            'sources':provenance,'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    target.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    print('UKI COMPARISON',target.relative_to(REPO))


if __name__=='__main__':
    main()
