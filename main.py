
import os
import re
import requests
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional 

from fastapi.middleware.cors import CORSMiddleware
import dotenv

# 从 upload_script 导入所有配置和执行函数
from upload_script import PRODUCT_FAMILY_BASE_PATHS, PRODUCT_TO_ACTION_NAME_MAP, execute_upload_tasks, FIXED_JSON_PATHS

# --- 初始化和配置 ---
dotenv.load_dotenv()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

EP_HOST = "https://ep.momenta.works"
# EP_API_TOKEN = os.getenv("EP_API_TOKEN")

# --- API 模型 ---
class UploadRequest(BaseModel):
    pipeline_url: str
    date_version: str
    custom_token: Optional[str] = None
    products: List[str]

def extract_task_id_from_url(url: str) -> Optional[str]:
    match = re.search(r"/tasks/([a-f0-9]+)", url)
    return match.group(1) if match else None

def update_env_token(new_token: str):
    """
    安全地查找并更新 .env 文件中的 EP_API_TOKEN。
    """
    try:
        dotenv_path = dotenv.find_dotenv()
        if not dotenv_path:
            # 如果没有 .env 文件，则创建一个
            with open(".env", "w") as f:
                f.write(f"EP_API_TOKEN={new_token}\n")
            dotenv_path = ".env"
            print("   - ✨ 未找到 .env 文件，已自动创建。")

        # 使用 set_key 安全地更新或添加 EP_API_TOKEN
        dotenv.set_key(dotenv_path, "EP_API_TOKEN", new_token)
        print(f"   - ✨ .env 文件中的 EP_API_TOKEN 已更新。")
        return True
    except Exception as e:
        print(f"   - ❌ 更新 .env 文件失败: {e}")
        return False

def generate_dynamic_target_path(product_key: str, date_version: str) -> Optional[str]:
    """根据产品名和日期版本，动态生成上传的目标路径"""
    family = None
    if product_key.startswith("ST35"):
        family = "ST35"
    elif product_key.startswith("ST3"):
        family = "ST3"
    
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

    current_token_from_env = os.getenv("EP_API_TOKEN")
    token_for_this_request = current_token_from_env # 默认使用环境变量中的 token
    
    # 检查前端是否传入了有效的、非空的新 token
    new_token_provided = request.custom_token and request.custom_token.strip()
    if new_token_provided:
        print("   - 发现前端输入了新的 Token。")
        # 1. 本次请求将使用这个新 token
        token_for_this_request = request.custom_token
        # 2. 检查新 token 是否与已存的 token 不同
        if token_for_this_request != current_token_from_env:
            # 3. 如果不同，则更新 .env 文件以备将来使用
            update_env_token(token_for_this_request)
        else:
            print("   - 新 Token 与已存 Token 相同，无需更新 .env 文件。")
        # print("   - 使用的 Token 来源: 前端自定义输入")
    else:
        print("   - 使用的 Token 来源: 环境变量 (.env)")

    # 检查最终是否有可用的 Token
    if not token_for_this_request:
        raise HTTPException(status_code=401, detail="认证失败：未提供任何 Token。请在 .env 文件或前端输入框中提供。")
    # --- Token 处理逻辑结束 ---

    api_data = {}
    dynamic_products_requested = any(p not in FIXED_JSON_PATHS for p in request.products)
    
    if dynamic_products_requested:
        if not request.pipeline_url:
            return [{"product": p, "status": "error", "message": "需要动态获取路径，但未提供 Pipeline URL。"} for p in request.products if p not in FIXED_JSON_PATHS]
        
        task_id = extract_task_id_from_url(request.pipeline_url)
        if not task_id:
            raise HTTPException(status_code=400, detail="URL格式错误，无法解析Task ID")
        
        api_url = f"{EP_HOST}/backend/pipeline/api/pipelines/result/{task_id}"
        # 使用最终决定的 token_for_this_request
        headers = {"Authorization": f"Bearer {token_for_this_request}"}
        
        print(f"➡️  步骤 1: 正在调用 EP API (ID: {task_id})...")
        try:
            response = requests.get(api_url, headers=headers, timeout=15)
            response.raise_for_status()
            api_data = response.json()
            print("   - ✅ EP API 调用成功。")
        except requests.exceptions.Timeout:
             print("   - ❌ EP API 调用超时！容器可能无法访问外部网络。")
             raise HTTPException(status_code=504, detail="调用 EP API 超时，请检查容器网络。")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [401, 403]:
                 raise HTTPException(status_code=e.response.status_code, detail="认证失败(401/403): Token 无效或已过期，请尝试在前端输入新的Token。")
            raise HTTPException(status_code=e.response.status_code, detail=f"调用 EP API 失败: {e.response.text}")
        except Exception as e:
            return [{"product": p, "status": "error", "message": f"调用 EP API 失败: {str(e)}"} for p in request.products]

    print(f"\n➡️  步骤 2: 正在构建上传任务...")

    upload_tasks = build_upload_tasks(api_data, request.products, request.date_version)

    # print(upload_tasks)
     # 3. 执行上传任务
    print(f"\n➡️  步骤 3: 开始执行上传...")
    # final_results 是一个包含每个文件上传结果的详细列表
    final_results = execute_upload_tasks(upload_tasks)
    
    # --- 新的、以完整路径为核心的结果聚合逻辑 ---
    
    # 最终要返回给前端的结果列表
    aggregated_results_list = []
    
    # 遍历前端请求的每一个产品，为它们生成一个最终状态
    for product_key in request.products:
        
        # 筛选出属于当前产品的所有任务结果
        results_for_this_product = [res for res in final_results if res['product'] == product_key]
        
        # 准备用于聚合的数据结构
        successful_full_paths = []
        failed_items = []
        
        # 遍历当前产品的所有上传结果
        for res in results_for_this_product:
            if res['status'] == 'success':
                # 1. 从 obs_path 提取文件名
                filename = os.path.basename(res.get('obs_path', ''))
                if filename:
                    # 2. 拼接成最终的完整路径 (使用 os.path.join 更安全)
                    full_target_path = os.path.join(res.get('target_path', ''), filename)
                    # 在 Windows 上 os.path.join 可能使用反斜杠，我们统一替换为正斜杠
                    successful_full_paths.append(full_target_path.replace('\\', '/'))
            else:
                failed_items.append({
                    "obs_path": res.get('obs_path'),
                    "reason": res.get('message')
                })

        # 现在根据聚合的数据，为产品生成最终的摘要
        product_summary = {
            "product": product_key,
            "status": "error", # 默认失败
            "message": "",
            "uploaded_paths": successful_full_paths # 无论成功失败，都返回成功上传的列表
        }

        # 判断情况 1: 这个产品连有效的上传任务都没有构建出来
        if not results_for_this_product:
            product_summary['message'] = "未能构建上传任务，请检查后端日志和配置。"
        
        # 判断情况 2: 有失败项
        elif failed_items:
            success_count = len(successful_full_paths)
            error_count = len(failed_items)
            product_summary['status'] = 'error'
            product_summary['message'] = f"部分文件上传失败 (成功: {success_count}, 失败: {error_count})"
            product_summary['failed_files'] = failed_items # 附带上失败的详细信息
            
        # 判断情况 3: 全部成功
        else:
            product_summary['status'] = 'success'
            product_summary['message'] = f"全部上传成功 ({len(successful_full_paths)}个文件)"

        aggregated_results_list.append(product_summary)

    # 打印最终的摘要日志
    print("\n📊 --- 最终产品聚合结果摘要 ---")
    for result in aggregated_results_list:
        icon = "✅" if result['status'] == 'success' else "❌"
        print(f"   {icon} {result['product']}: {result['message']}")
        # 打印成功上传的路径
        for path in result.get('uploaded_paths', []):
            print(f"     - {path}")

    print("\n✅ --- 所有任务处理完成。---")
    return aggregated_results_list