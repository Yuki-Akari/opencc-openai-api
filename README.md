如果你使用的翻译工具只支持ai api并且只需要繁简转换的话，比如翻译繁体漫画，可以用这个伪装成openai兼容提供翻译服务
省去了token费，也不会有ai乱改标点的问题 


启动服务：python convert_api.py



api地址填http://127.0.0.1:8000/v1



windows打包成exe：pyinstaller -F -c convert_api.py



| 模型标识 | 转换功能 |
| ---- | ---- |
| s2t | 简体中文 → 繁体中文 |
| t2s | 繁体中文 → 简体中文 |
| s2tw | 简体 → 台湾繁体 |
| tw2s | 台湾繁体 → 简体 |
| s2hk | 简体 → 香港繁体 |
| hk2s | 香港繁体 → 简体 |



真的会有人用吗🤔
