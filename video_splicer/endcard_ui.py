from __future__ import annotations

from collections.abc import Callable

from video_splicer.endcard_store import EndcardUploadError, replace_endcard_upload

ENDCARD_UPLOAD_SUCCESS_MESSAGE = "新落版已保存，后续新发起的拼接任务将使用该文件。"
ENDCARD_UPLOAD_INPUT_SELECTOR = 'input[type="file"][accept*=".mov"]'
ENDCARD_UPLOAD_TRIGGER_ID = "sp-endcard-upload-trigger"


def build_endcard_upload_widget_key(version: int) -> str:
    return f"sp_endcard_upload_file_{version}"


def build_endcard_upload_trigger_html() -> str:
    return f"""
<div class="sp-endcard-upload-trigger-wrap">
  <button id="{ENDCARD_UPLOAD_TRIGGER_ID}" class="sp-endcard-upload-trigger" type="button">更换落版</button>
</div>
<style>
  .sp-endcard-upload-trigger-wrap {{
    width: 100%;
  }}

  .sp-endcard-upload-trigger {{
    width: 100%;
    min-height: 2.5rem;
    padding: 0.5rem 1rem;
    border: 1px solid rgba(49, 51, 63, 0.2);
    border-radius: 0.5rem;
    background: #ffffff;
    color: rgb(49, 51, 63);
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.2;
    cursor: pointer;
  }}

  .sp-endcard-upload-trigger:hover {{
    background: rgb(246, 247, 249);
  }}

  .sp-endcard-upload-trigger:focus {{
    outline: 2px solid rgba(255, 75, 75, 0.35);
    outline-offset: 1px;
  }}
</style>
<script>
  (() => {{
    const triggerId = "{ENDCARD_UPLOAD_TRIGGER_ID}";
    const uploaderSelector = {ENDCARD_UPLOAD_INPUT_SELECTOR!r};

    const hideUploader = (uploaderInput) => {{
      const uploaderRoot =
        uploaderInput.closest('[data-testid="stFileUploader"]') ||
        uploaderInput.closest('[data-testid="stFileUploaderDropzone"]');
      if (!uploaderRoot || uploaderRoot.dataset.spEndcardHidden === "1") {{
        return;
      }}

      uploaderRoot.dataset.spEndcardHidden = "1";
      Object.assign(uploaderRoot.style, {{
        position: "absolute",
        left: "-9999px",
        top: "0",
        width: "1px",
        height: "1px",
        overflow: "hidden",
        opacity: "0",
        pointerEvents: "none",
      }});
    }};

    const bindTrigger = () => {{
      const trigger = document.getElementById(triggerId);
      const uploaderInput = document.querySelector(uploaderSelector);
      if (!trigger || !uploaderInput) {{
        return false;
      }}

      hideUploader(uploaderInput);
      if (trigger.dataset.bound === "1") {{
        return true;
      }}

      trigger.dataset.bound = "1";
      trigger.addEventListener("click", (event) => {{
        event.preventDefault();
        uploaderInput.click();
      }});
      return true;
    }};

    bindTrigger();

    if (window.__spEndcardUploadObserver) {{
      window.__spEndcardUploadObserver.disconnect();
    }}

    const observer = new MutationObserver(() => {{
      bindTrigger();
    }});
    observer.observe(document.body, {{ childList: true, subtree: true }});
    window.__spEndcardUploadObserver = observer;
  }})();
</script>
"""


def save_endcard_upload(
    upload_name: str,
    upload_bytes: bytes,
    replace_upload_fn: Callable[..., object] = replace_endcard_upload,
) -> tuple[str, str]:
    try:
        replace_upload_fn(upload_name=upload_name, upload_bytes=upload_bytes)
    except EndcardUploadError as exc:
        return "", str(exc)
    except Exception as exc:  # noqa: BLE001
        return "", f"落版视频保存失败：{exc}"

    return ENDCARD_UPLOAD_SUCCESS_MESSAGE, ""
