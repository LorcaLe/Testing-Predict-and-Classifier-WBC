"""Isolated, time-bounded document processing child process."""

import json
import sys

from common import storage
from common.contracts import WatermarkSettings
from common.pdf import UnsupportedDocument, add_watermark, preview_pages


def run(payload):
    data = payload["data"]
    prefix = f"documents/{data['document_id']}/jobs/{payload['job_id']}"
    if payload["type"] == "ProcessingRequested":
        result = add_watermark(storage.get(data["source_key"]), WatermarkSettings.model_validate(data["settings"]))
        key = f"{prefix}/result.pdf"
        storage.put(key, result, "application/pdf")
        return {"result_key": key}
    result = {"original": [], "result": []}
    for variant, source in (("original", data["source_key"]), ("result", data["result_key"])):
        for index, png in preview_pages(storage.get(source)):
            key = f"{prefix}/preview/{variant}/{index}.png"
            storage.put(key, png, "image/png")
            result[variant].append(key)
    return {"previews": result}


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin))))
    except UnsupportedDocument as error:
        print(json.dumps({"permanent_error": str(error)}))
        sys.exit(2)

