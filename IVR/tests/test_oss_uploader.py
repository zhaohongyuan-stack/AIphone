"""
OSS 测试报告上传工具
- 将测试报告 JSON 上传到 OSS
- OSS 未配置时降级为本地文件保存
- 供 pytest 测试和 DB 同事导出脚本共用
"""
import json
import os
from datetime import datetime
from typing import Union

from config import settings


def is_oss_configured() -> bool:
    """检测 OSS 配置是否完整"""
    return all([
        settings.OSS_ENDPOINT,
        settings.OSS_ACCESS_KEY_ID,
        settings.OSS_ACCESS_KEY_SECRET,
        settings.OSS_BUCKET_NAME,
    ])


def upload_report(data: Union[dict, list, str], report_name: str,
                  reports_dir: str = "test-reports") -> dict:
    """
    上传测试报告到 OSS

    Args:
        data: 报告内容（dict/list 自动序列化为 JSON，str 直接写入）
        report_name: 报告文件名（如 "test_ivr_routing_report.json"）
        reports_dir: OSS 上的目录名

    Returns:
        {
            "ok": bool,          # 是否成功（含降级）
            "location": str,     # OSS URL 或本地文件路径
            "fallback": bool,    # 是否降级到本地
            "message": str,      # 说明信息
        }
    """
    # 序列化内容
    if isinstance(data, (dict, list)):
        content = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        content = str(data)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    object_key = f"{reports_dir}/{timestamp}_{report_name}"

    # OSS 未配置 → 降级到本地
    if not is_oss_configured():
        return _save_local(content, timestamp, report_name,
                           "OSS 未配置，报告已保存到本地")

    # 真实上传
    try:
        import oss2
        auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID,
                         settings.OSS_ACCESS_KEY_SECRET)
        bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT,
                             settings.OSS_BUCKET_NAME)
        bucket.put_object(object_key, content)
        url = (f"https://{settings.OSS_BUCKET_NAME}."
               f"{settings.OSS_ENDPOINT}/{object_key}")
        return {
            "ok": True,
            "location": url,
            "fallback": False,
            "message": "已上传到 OSS",
        }
    except Exception as e:
        return _save_local(content, timestamp, report_name,
                           f"OSS 上传失败: {e}，已降级到本地")


def _save_local(content: str, timestamp: str, report_name: str,
                message: str) -> dict:
    """降级：保存到本地文件"""
    local_dir = os.path.join("test-reports", "local")
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{timestamp}_{report_name}")
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)
    return {
        "ok": True,
        "location": local_path,
        "fallback": True,
        "message": message,
    }


# ═══════════════════════════════════════════════════════════════
#  pytest 测试
# ═══════════════════════════════════════════════════════════════

def test_oss_config_check():
    """验证 OSS 配置检测函数正常工作"""
    result = is_oss_configured()
    assert isinstance(result, bool)


def test_upload_report_fallback():
    """测试报告上传（OSS 未配置时降级到本地，配置时上传 OSS）"""
    sample = {
        "test_suite": "test_oss_uploader",
        "passed": True,
        "timestamp": datetime.now().isoformat(),
        "data": [{"id": 1, "name": "test_case_1"},
                 {"id": 2, "name": "test_case_2"}],
    }
    result = upload_report(sample, "oss_uploader_selftest.json")

    assert result["ok"] is True
    assert "location" in result
    assert "fallback" in result

    # 验证文件存在
    if result["fallback"]:
        assert os.path.exists(result["location"])
        # 清理测试文件
        os.remove(result["location"])
