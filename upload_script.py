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


# 定义每个产品最终的上传目标文件夹路径
PRODUCT_FAMILY_BASE_PATHS: Dict[str, str] = {
    "ST3": "panguprodmmt/Momenta/167/NCD2442/test/",
    "ST35": "panguprodmmt/Momenta/174/NCD2442/test/",
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
    执行一个上传任务列表，并返回每个任务的详细结果。
    
    返回的每个结果字典都包含 status, obs_path, 和 target_path，
    以便上层调用者可以构建完整的最终路径。
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
        print(f"       - 目标文件夹: {target_path}")

        payload = {"obs_path": obs_path, "target_path": target_path}
        
        try:
            response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=300)
            
            # --- 核心修改：返回更清晰、更有用的字段 ---
            if response.status_code == 200:
                result_detail = {
                    "product": product_key,
                    "status": "success",
                    "message": "上传成功",
                    "obs_path": obs_path,       # 明确返回源路径
                    "target_path": target_path  # 明确返回目标文件夹路径
                }
            else:
                result_detail = {
                    "product": product_key,
                    "status": "error",
                    # 返回更详细的错误信息
                    "message": f"上传失败 (状态码: {response.status_code}, 详情: {response.text})",
                    "obs_path": obs_path,
                    "target_path": target_path
                }
                
        except Exception as e:
            result_detail = {
                "product": product_key,
                "status": "error",
                "message": f"网络请求异常: {str(e)}",
                "obs_path": obs_path,
                "target_path": target_path
            }
        
        print(f"       - 结果: {result_detail['status']} - {result_detail['message']}")
        upload_results.append(result_detail)
            
    return upload_results