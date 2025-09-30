# main.py (Python 3.7 兼容版)

import os
import re
import requests
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional # 1. 导入 Optional

from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 从 upload_script 导入所有配置和执行函数
from upload_script import TARGET_PATH_TEMPLATES, PRODUCT_TO_ACTION_NAME_MAP, execute_upload_tasks, FIXED_JSON_PATHS

# --- 初始化和配置 ---
load_dotenv()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EP_HOST = "https://ep.momenta.works"
EP_API_TOKEN = os.getenv("EP_API_TOKEN")

# --- API 模型 ---
class UploadRequest(BaseModel):
    pipeline_url: str
    products: List[str]

# --- 辅助函数 ---
# 2. 修改类型提示
def extract_task_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/tasks/([a-f0-9]+)", url)
    return match.group(1) if match else None

def extract_paths_from_action(proc_act_name: str, action: Dict, result_dict: Dict, product_key: str) -> List[str]:
    """
    根据 action 名称和类型，从 result 字典中提取路径。
    (Python 3.7 兼容版)
    """
    paths_to_add = []
    
    # 规则 1: 处理 SOP 类型的 Action
    if "SOP" in proc_act_name.upper() and action.get("action_type") == "harz_package_and_upload":
        # print(f"     - 应用规则 [SOP & harz_package_and_upload]")
        shadow_path = result_dict.get("shadow_obs_path")
        if shadow_path:
            paths_to_add.append(shadow_path)
        
        package_path = result_dict.get("package_obs_path")
        if package_path:
            paths_to_add.append(package_path)

    # 规则 2: 处理 IFS 类型的 Action
    elif "IFS" in proc_act_name.upper():
        # print(f"     - 应用规则 [IFS]")
        # 3. 改写海象运算符
        lib_path = result_dict.get("lib_obs_path")
        if lib_path: 
            paths_to_add.append(lib_path)
        
        # 如果是 PROD 产品，额外检查 config_obs_path
        if product_key.endswith("_PROD"):
            # 3. 改写海象运算符
            config_path = result_dict.get("config_obs_path")
            if config_path: 
                paths_to_add.append(config_path)

    # 规则 3: 处理包含 " sop " (带空格) 的 Action
    elif " sop " in proc_act_name.lower():
        # print(f"     - 应用规则 [' sop ' dev/prod]")
        rvc_path = result_dict.get("rvc_obs_path")
        if rvc_path:
            paths_to_add.append(rvc_path)
            
        config_path = result_dict.get("config_obs_path")
        if config_path:
            paths_to_add.append(config_path)
        
    return paths_to_add


def build_upload_tasks(api_data: Dict[str, Any], requested_products: List[str]) -> List[Dict[str, str]]:
    """
    从 API 响应中根据清晰的规则，解析并构建上传任务列表 (V3 - 健壮版)。
    """
    tasks = []
    action_list = api_data.get("data", {}).get("action_task_list", [])
    
    for product_key in requested_products:
        target_path = TARGET_PATH_TEMPLATES.get(product_key)
        if not target_path:
            print(f"   - ⚠️  跳过 '{product_key}': 未在 TARGET_PATH_TEMPLATES 中配置目标路径。")
            continue

        if product_key in FIXED_JSON_PATHS:
            obs_path = FIXED_JSON_PATHS[product_key]
            print(f"\n--- 正在为产品 '{product_key}' 应用固定路径规则 ---")
            print(f"   - ✅ 提取到固定路径: {obs_path}")
            tasks.append({"product_key": product_key, "obs_path": obs_path, "target_path": target_path})
            continue

        action_names_for_this_product = PRODUCT_TO_ACTION_NAME_MAP.get(product_key, [])
        if not action_names_for_this_product:
            print(f"\n--- 正在为产品 '{product_key}' 寻找路径 ---")
            print(f"   - ⚠️  跳过 '{product_key}': 未在 PRODUCT_TO_ACTION_NAME_MAP 中配置。")
            continue
            
        print(f"\n--- 正在为产品 '{product_key}' 寻找路径 ---")
        print(f"   - 它关心以下 Actions: {action_names_for_this_product}")
        
        found_paths_for_this_product = []
        for action in action_list:
            proc_act_name = action.get("proc_act_name")
            if proc_act_name not in action_names_for_this_product:
                continue

            result_dict = action.get("result", {})
            paths_from_action = extract_paths_from_action(proc_act_name, action, result_dict, product_key)
            
            if paths_from_action:
                found_paths_for_this_product.extend(paths_from_action)
            else:
                print(f"     - ⚠️  在 '{proc_act_name}' 中未根据规则提取到任何路径。")

        if found_paths_for_this_product:
            print(f"   - ✨ 总结: 为 '{product_key}' 共找到 {len(found_paths_for_this_product)} 个路径，正在创建任务...")
            for obs_path in found_paths_for_this_product:
                print(f"     - 添加任务: {obs_path}")
                tasks.append({
                    "product_key": product_key,
                    "obs_path": obs_path,
                    "target_path": target_path
                })
        else:
            print(f"   - ❌ 总结: 未能为 '{product_key}' 找到任何有效的 OBS 路径。请检查 API 响应或配置。")
                 
    return tasks


# --- API 端点 ---
@app.post("/api/start-upload")
def start_upload_process(request: UploadRequest):
    print("\n" + "="*50)
    print("✅ --- 收到 POST 请求 ---") # 2. 修改了日志，确认 POST 请求已进入

    api_data = {}
    dynamic_products_requested = any(p not in FIXED_JSON_PATHS for p in request.products)
    
    if dynamic_products_requested:
        if not request.pipeline_url:
             return [{"product": p, "status": "error", "message": "需要动态获取路径，但未提供 Pipeline URL。"} for p in request.products if p not in FIXED_JSON_PATHS]
        
        task_id = extract_task_id_from_url(request.pipeline_url)
        if not task_id:
            return [{"product": p, "status": "error", "message": "URL格式错误，无法解析Task ID"} for p in request.products]
        
        api_url = f"{EP_HOST}/backend/pipeline/api/pipelines/result/{task_id}"
        headers = {"Authorization": f"Bearer {EP_API_TOKEN}"}
        
        print("➡️  步骤 1: 正在调用 EP API...")
        try:
            response = requests.get(api_url, headers=headers, timeout=15) # 3. 增加了超时设置
            response.raise_for_status()
            api_data = response.json()
            print("   - ✅ EP API 调用成功。")
        except requests.exceptions.Timeout:
             print("   - ❌ EP API 调用超时！容器可能无法访问外部网络。")
             raise HTTPException(status_code=504, detail="调用 EP API 超时，请检查容器网络。")
        except Exception as e:
            return [{"product": p, "status": "error", "message": f"调用 EP API 失败: {str(e)}"} for p in request.products]

    print(f"\n➡️  步骤 2: 正在构建上传任务...")
    upload_tasks = build_upload_tasks(api_data, request.products)
    # print(upload_tasks)
    # print(f"\n➡️  步骤 3: 开始执行上传...")
    # final_results = execute_upload_tasks(upload_tasks)
    
    # all_final_results = []
    # processed_products = {res['product'] for res in final_results}
    
    # all_final_results.extend(final_results)
    
    # for product in request.products:
    #     if product not in processed_products:
    #         all_final_results.append({
    #             "product": product,
    #             "status": "error",
    #             "message": "未能构建上传任务，请检查后端日志和配置。"
    #         })

    # print("\n✅ --- 所有任务处理完成。---")
    # return all_final_results