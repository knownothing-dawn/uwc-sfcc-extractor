"""Run the canonical unittest suite and synchronize documented total counts."""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def update_test_count_text(text, count):
    text=re.sub(r'tests-\d+%20passed',f'tests-{count}%20passed',text)
    text=re.sub(r'Ran \d+ tests',f'Ran {count} tests',text)
    text=re.sub(r'总计：\d+/\d+ 通过',f'总计：{count}/{count} 通过',text)
    text=re.sub(r'测试总数：\d+',f'测试总数：{count}',text)
    return text


def run_and_update(root, files, report=None):
    command=[sys.executable,'-m','unittest','discover','-s',str(root/'tests'),'-v']
    completed=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
    output=completed.stdout+'\n'+completed.stderr
    match=re.search(r'Ran (\d+) tests',output)
    if completed.returncode or not match:
        raise RuntimeError(output)
    count=int(match.group(1))
    for path in files:
        if path.exists(): path.write_text(update_test_count_text(path.read_text(encoding='utf-8'),count),encoding='utf-8')
    if report:
        report.parent.mkdir(parents=True,exist_ok=True);report.write_text(output,encoding='utf-8')
    return count,output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--document',type=Path,action='append',default=[])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    count,output=run_and_update(args.root.resolve(),[p.resolve() for p in args.document],args.report.resolve() if args.report else None)
    print(f'Ran {count} tests; documentation synchronized.')


if __name__=='__main__': main()
