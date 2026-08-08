import time
import uuid
import json
import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Any
from opencc import OpenCC

# 初始化服务
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 预加载所有常用转换方向
converters = {
    "s2t": OpenCC("s2t"),
    "t2s": OpenCC("t2s"),
    "s2tw": OpenCC("s2tw"),
    "tw2s": OpenCC("tw2s"),
    "s2hk": OpenCC("s2hk"),
    "hk2s": OpenCC("hk2s"),
}

# 默认转换方向（工具不指定模型时生效，可自行修改）
DEFAULT_CONVERTER = "s2t"

# OpenAI 请求格式定义
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None

# 判断字符串中是否包含汉字（用于检测需要繁简转换的字段）
_cjk_re = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufa2f\u3000-\u303f]")

def contains_cjk(s: str) -> bool:
    return bool(_cjk_re.search(s))


def convert_json_like(obj: Any, converter: OpenCC) -> Any:
    """
    递归遍历 JSON 可序列化对象，只对包含汉字的字符串进行繁简转换，保留其他字段（如位置信息、字体大小等）原样。
    这样可以保证返回的 JSON 结构和布局元数据不变，只替换文字内容。
    """
    if isinstance(obj, dict):
        return {k: convert_json_like(v, converter) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_json_like(i, converter) for i in obj]
    elif isinstance(obj, str):
        # 只转换包含汉字的字符串，避免把非中文文本（如字体名、数值、标识符）改变
        if contains_cjk(obj):
            return converter.convert(obj)
        else:
            return obj
    else:
        return obj


# 核心接口：完全兼容 OpenAI /v1/chat/completions
@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    # 提取最后一条用户消息
    user_text = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_text = msg.content
            break

    # 根据模型名自动匹配转换方向
    converter_key = DEFAULT_CONVERTER
    for key in converters.keys():
        if key in request.model.lower():
            converter_key = key
            break

    converter = converters[converter_key]

    # 先尝试将用户输入解析为 JSON（常见的图像翻译工具会把文字位置、大小、颜色等元数据以 JSON 结构传入）
    converted_str: str
    try:
        parsed = json.loads(user_text)
        # 如果解析成功，递归替换包含汉字的字符串字段，不改变结构
        processed = convert_json_like(parsed, converter)
        # 保持原有的 JSON 格式（UTF-8 不转义）
        converted_str = json.dumps(processed, ensure_ascii=False)
    except Exception:
        # 不是 JSON：按原先行为直接对整个字符串执行转换
        converted_str = converter.convert(user_text)

    # 非流式返回（标准 OpenAI 格式）
    if not request.stream:
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": converted_str},
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(user_text),
                "completion_tokens": len(converted_str),
                "total_tokens": len(user_text) + len(converted_str)
            }
        }

    # 流式返回（兼容 SSE 格式）
    def stream_generator():
        for char in converted_str:
            chunk = {
                "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{"index": 0, "delta": {"content": char}, "finish_reason": None}]
            }
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


# 模型列表接口，部分工具会调用校验
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": k, "object": "model", "owned_by": "local"} for k in converters.keys()]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
