# upload_script.py

import requests
import json
from typing import List, Dict, Any

# ==========================================================
#                  网络配置
# ==========================================================
API_URL = "http://10.21.15.30:8087/upload/"
HEADERS = {
    "accept": "application/json",
    "Content-Type": "application/json"
}

# ==========================================================
#                  核心业务配置 (单一事实来源)
# ==========================================================

# 定义每个产品最终的上传目标文件夹路径
TARGET_PATH_TEMPLATES: Dict[str, str] = {
    "ST35_DEV": "panguprodmmt/Momenta/174/NCD2442/dev/20250925_A082.03/",
    "ST35_PROD": "panguprodmmt/Momenta/174/NCD2442/prod/20250925_A082.03/",
    "ST3_DEV": "panguprodmmt/Momenta/167/NCD2442/dev/20250925_A182.03/",
    "ST3_PROD": "panguprodmmt/Momenta/167/NCD2442/prod/20250925_A182.03/",
    "ST3_DEV_json": "panguprodmmt/Momenta/167/NCD2442/dev/20250925_A182.03/",
    "ST3_PROD_json": "panguprodmmt/Momenta/167/NCD2442/prod/20250925_A182.03/",
    "ST35_DEV_json": "panguprodmmt/Momenta/174/NCD2442/dev/20250925_A082.03/",
    "ST35_PROD_json": "panguprodmmt/Momenta/174/NCD2442/prod/20250925_A082.03/",
}

# 定义每个【动态产品】需要从哪些 API Action 中提取信息
PRODUCT_TO_ACTION_NAME_MAP: Dict[str, List[str]] = {
    "ST35_DEV": ["ST35 DEV SOP", "ST35 IFS", "st35 sop dev"],
    "ST35_PROD": ["ST35 PROD SOP", "ST35 IFS", "st35 sop prod"],
    "ST3_DEV": ["ST3 DEV SOP", "ST3 IFS", "st3 sop dev"],
    "ST3_PROD": ["ST3  PROD SOP", "ST3 IFS", "st3 sop prod"],
}

FIXED_JSON_PATHS = {
    "ST3_DEV_json": "obs://harz-data-obs/vertical_version/vertical_package_config/ST3_dev/test.json",
    "ST3_PROD_json": "obs://harz-data-obs/vertical_version/vertical_package_config/ST3_prod/test.json",
    "ST35_DEV_json": "obs://harz-data-obs/vertical_version/vertical_package_config/ST35_dev/test.json",
    "ST35_PROD_json": "obs://harz-data-obs/vertical_version/vertical_package_config/ST35_prod/test.json",
}

# ==========================================================
#                  上传执行函数
# ==========================================================

def execute_upload_tasks(tasks: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """
    执行一个上传任务列表，并返回每个任务的结果。

    Args:
        tasks: 一个任务字典的列表，每个字典必须包含 'product_key', 'obs_path', 'target_path'。

    Returns:
        一个包含每个任务简洁上传结果的列表。
    """
    upload_results = []

    if not tasks:
        print("   - 没有需要执行的上传任务。")
        return upload_results

    for task in tasks:
        obs_path = task['obs_path']
        target_path = task['target_path']
        product_key = task['product_key']
        
        print(f"     - 正在上传 '{product_key}':")
        print(f"       - 源: {obs_path}")
        print(f"       - 目标: {target_path}")

        payload = {"obs_path": obs_path, "target_path": target_path}
        result_detail = {}
        
        try:
            # 设置较长的超时时间，以防大文件上传耗时
            response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=300)
            
            if response.status_code == 200:
                result_detail = {
                    "product": product_key,
                    "status": "success",
                    "message": "上传成功"
                }
            else:
                result_detail = {
                    "product": product_key,
                    "status": "error",
                    "message": f"上传失败 (状态码: {response.status_code})"
                }
                
        except Exception as e:
            result_detail = {
                "product": product_key,
                "status": "error",
                "message": f"网络请求异常: {str(e)}"
            }
        
        print(f"       - 结果: {result_detail['status']} - {result_detail['message']}")
        upload_results.append(result_detail)
            
    return upload_results