
import os
import re
import requests
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional 

from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# 从 upload_script 导入所有配置和执行函数
from upload_script import PRODUCT_FAMILY_BASE_PATHS, PRODUCT_TO_ACTION_NAME_MAP, execute_upload_tasks, FIXED_JSON_PATHS

# --- 初始化和配置 ---
load_dotenv()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EP_HOST = "https://ep.momenta.works"
EP_API_TOKEN = os.getenv("EP_API_TOKEN")

# --- API 模型 ---
class UploadRequest(BaseModel):
    pipeline_url: str
    date_version: str  
    products: List[str]


def extract_task_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/tasks/([a-f0-9]+)", url)
    return match.group(1) if match else None

def generate_dynamic_target_path(product_key: str, date_version: str) -> Optional[str]:
    """根据产品名和日期版本，动态生成上传的目标路径"""
    family = None
    if product_key.startswith("ST3"):
        family = "ST3"
    elif product_key.startswith("ST35"):
        family = "ST35"
    
    if not family:
        print(f"   - ❌ 无法为 '{product_key}' 确定产品家族 (ST3/ST35)。")
        return None

    base_path = PRODUCT_FAMILY_BASE_PATHS.get(family)
    if not base_path:
        print(f"   - ❌ 未在 PRODUCT_FAMILY_BASE_PATHS 中找到 '{family}' 的基础路径。")
        return None

    env_part = None
    if "DEV" in product_key:
        env_part = "dev/"
    elif "PROD" in product_key:
        env_part = "prod/"
    
    if not env_part:
        print(f"   - ❌ 无法为 '{product_key}' 确定环境 (DEV/PROD)。")
        return None
        
    # 清理用户输入，并确保路径以斜杠结尾
    clean_date_version = date_version.strip('/')
    
    final_path = f"{base_path}{env_part}{clean_date_version}/"
    print(f"   - ✨ 为 '{product_key}' 生成动态路径: {final_path}")
    return final_path

def extract_paths_from_action(proc_act_name: str, action: Dict, result_dict: Dict, product_key: str) -> List[str]:
    """
    根据 action 名称和类型，从 result 字典中提取路径。
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


def build_upload_tasks(api_data: Dict[str, Any], requested_products: List[str], date_version: str) -> List[Dict[str, str]]:
    tasks = []
    action_list = api_data.get("data", {}).get("action_task_list", [])
    
    for product_key in requested_products:
        # 1. 动态生成目标路径
        target_path = generate_dynamic_target_path(product_key, date_version)
        if not target_path:
            print(f"   - ⚠️  跳过 '{product_key}': 无法为其生成有效的动态目标路径。")
            continue

        # 2. 处理固定路径的 JSON 文件
        if product_key in FIXED_JSON_PATHS:
            obs_path = FIXED_JSON_PATHS[product_key]
            tasks.append({"product_key": product_key, "obs_path": obs_path, "target_path": target_path})
            continue

        # 3. 处理动态路径的产品
        action_names_for_this_product = PRODUCT_TO_ACTION_NAME_MAP.get(product_key, [])
        if not action_names_for_this_product:
            print(f"   - ⚠️  跳过 '{product_key}': 未在 PRODUCT_TO_ACTION_NAME_MAP 中配置。")
            continue
        
        found_paths_for_this_product = []
        for action in action_list:
            if action.get("proc_act_name") in action_names_for_this_product:
                paths = extract_paths_from_action(action["proc_act_name"], action, action.get("result", {}), product_key)
                found_paths_for_this_product.extend(paths)

        for obs_path in found_paths_for_this_product:
            tasks.append({"product_key": product_key, "obs_path": obs_path, "target_path": target_path})
            
    return tasks


# --- API 端点 ---
@app.post("/api/start-upload")
def start_upload_process(request: UploadRequest):
    print("\n" + "="*50)
    print("✅ --- 收到 POST 请求 ---") 

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
            response = requests.get(api_url, headers=headers, timeout=15) 
            response.raise_for_status()
            api_data = response.json()
            print("   - ✅ EP API 调用成功。")
        except requests.exceptions.Timeout:
             print("   - ❌ EP API 调用超时！容器可能无法访问外部网络。")
             raise HTTPException(status_code=504, detail="调用 EP API 超时，请检查容器网络。")
        except Exception as e:
            return [{"product": p, "status": "error", "message": f"调用 EP API 失败: {str(e)}"} for p in request.products]

    print(f"\n➡️  步骤 2: 正在构建上传任务...")
    
    upload_tasks = build_upload_tasks(api_data, request.products, request.date_version)

    print(upload_tasks)
    print(f"\n➡️  步骤 3: 开始执行上传...")
    # final_results 是一个包含每个文件上传结果的详细列表
    final_results = execute_upload_tasks(upload_tasks)
       
    # 最终要返回给前端的结果列表
    aggregated_results_list = []
    # aggregated_results_list =[
    # {
    #     "product": "ST3_DEV",
    #     "status": "success",
    #     "message": "全部上传成功 (2个文件)"
    # },
    # {
    #     "product": "ST3_PROD",
    #     "status": "error",
    #     "message": "部分文件上传失败 (成功: 1, 失败: 1)"
    # },
    # {
    #     "product": "ST35_DEV",
    #     "status": "success",
    #     "message": "全部上传成功 (1个文件)"
    # }
    # ]
    # 遍历前端请求的每一个产品，为它们生成一个最终状态
    for product_key in request.products:
        
        # 筛选出属于当前产品的所有任务结果
        results_for_this_product = [res for res in final_results if res['product'] == product_key]
        
        # 最终的聚合结果
        product_summary = {
            "product": product_key,
            "status": "error", # 默认是 error
            "message": ""
        }

        # 判断情况 1: 这个产品连有效的上传任务都没有构建出来
        if not results_for_this_product:
            product_summary['message'] = "未能构建上传任务，请检查后端日志和配置。"
            aggregated_results_list.append(product_summary)
            continue # 处理下一个产品

        # 判断情况 2: 至少有一个文件上传失败
      
        has_errors = any(res['status'] == 'error' for res in results_for_this_product)
        if has_errors:
            # 统计成功和失败的数量，用于生成更详细的消息
            success_count = sum(1 for res in results_for_this_product if res['status'] == 'success')
            error_count = len(results_for_this_product) - success_count
            
            product_summary['status'] = 'error'
            product_summary['message'] = f"部分文件上传失败 (成功: {success_count}, 失败: {error_count})"
            aggregated_results_list.append(product_summary)
            continue # 处理下一个产品
            
        # 判断情况 3: 所有文件都上传成功
        # 如果代码能执行到这里，说明上面两个 if 都没触发，即所有文件都成功了
        product_summary['status'] = 'success'
        product_summary['message'] = f"全部上传成功 ({len(results_for_this_product)}个文件)"
        aggregated_results_list.append(product_summary)

    # 打印最终的摘要日志
    print("\n📊 --- 最终产品聚合结果摘要 ---")
    for result in aggregated_results_list:
        icon = "✅" if result['status'] == 'success' else "❌"
        print(f"   {icon} {result['product']}: {result['message']}")

    print("\n✅ --- 所有任务处理完成。---")
    return aggregated_results_list