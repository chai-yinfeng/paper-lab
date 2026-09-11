import argparse
import os
import uvicorn

parser = argparse.ArgumentParser(description="Paper Lab local reading workspace")
parser.add_argument(
    "--data-dir",
    help="User-selected data directory outside Git; otherwise choose in UI",
)
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()
if args.data_dir:
    os.environ["PAPER_LAB_DATA_DIR"] = args.data_dir
uvicorn.run("paper_lab.api:app", host="127.0.0.1", port=args.port)
