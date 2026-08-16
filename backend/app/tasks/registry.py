"""异步任务注册表。

task_type -> worker 映射与预算等待时间。新增异步任务只需在此登记一行，
工具层（submit_task/get_result）零改动。
"""

ASYNC_TASKS = {
    "video_cogvideox_flash": { #  工具来源：智谱AI开放平台
        "worker": "generate_video_task",
        "params": ["prompt"],
        "fast_timeout": 10,  # 视频不可能 10s 完成，尽早返回 task_id 走轮询
    },
}
