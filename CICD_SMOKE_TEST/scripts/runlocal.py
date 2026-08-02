import argparse
import subprocess
import sys
from pathlib import Path
import glob

def main() -> int:
    p = argparse.ArgumentParser(description="Run JMeter and post-process JTLs")
    a = p.parse_args()

    print("=================Test is Starting=================")

    scripts_dir = (Path(__file__).resolve().parent / ".." / "scripts").resolve()
    if scripts_dir.exists():
        for pat in ("*.jtl", "*.html"):
            for f in scripts_dir.glob(pat):
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass

    jm = "F:/apache-jmeter-5.6.3/bin/jmeter.bat"
    jmx = "F:/jmeter/CICD_SMOKE_TEST/free_api.jmx"
    subprocess.run([
        "cmd", "/c", jm, "-n", "-t", jmx,
    ], check=False)

    for jtl in Path.cwd().glob("*.jtl"):
        base = jtl.stem
        subprocess.run([sys.executable, "jreport_v2.py", str(jtl), base], check=False)
        htmls = glob.glob(f"{base}*.html")
        for h in htmls:
            print(h)

    print("==============================End============================")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())