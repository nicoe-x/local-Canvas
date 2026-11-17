import asyncio
import json
import os
import httpx
from fastapi import HTTPException, Request
from .h3_prompts import PromptRequest, messages, validate_result


def register(app, authenticate, transport=None, converter=None):
    prompt_busy=set()

    @app.post('/api/prompts/h3')
    async def h3_prompt(request:Request, body:PromptRequest):
        user=authenticate(request,write=True)
        if not body.source.strip() or any(not title.strip() or len(title)>200 for title in body.references):
            raise HTTPException(422,'描述和参考素材名称不能为空，素材名称最多200字')
        url=os.environ.get('STUDIO_TEXT_URL');model=os.environ.get('STUDIO_TEXT_MODEL')
        if converter is None and (not url or not model):
            raise HTTPException(501,'请配置 STUDIO_TEXT_URL 和 STUDIO_TEXT_MODEL，连接本地或自选的 OpenAI 兼容文本服务；转换不会调用视频模型')
        if user['id'] in prompt_busy:
            raise HTTPException(409,'已有提示词正在转换，请等待完成')
        prompt_busy.add(user['id'])
        headers={'Authorization':'Bearer '+os.environ['STUDIO_TEXT_KEY']} if os.environ.get('STUDIO_TEXT_KEY') else {}
        try:
            if converter is not None:
                value=await asyncio.to_thread(converter,messages(body))
                model='Qwen3.6-27B (local)'
            else:
                async with httpx.AsyncClient(timeout=180,trust_env=False,follow_redirects=False,transport=transport) as client:
                    result=await client.post(url.rstrip('/')+'/chat/completions',headers=headers,json={
                        'model':model,'messages':messages(body),'temperature':0.2,
                        'max_tokens':16000,'response_format':{'type':'json_object'}})
                    result.raise_for_status()
                    choice=result.json()['choices'][0]
                    if choice.get('finish_reason') == 'length':
                        raise HTTPException(422,'文本模型输出被截断，请缩短原文或目标时长后重新转换')
                    value=json.loads(choice['message']['content'])
            try:return {**validate_result(value,body),'model':model}
            except ValueError as error:raise HTTPException(422,'H3 格式复检未通过：'+str(error)) from None
        except HTTPException:raise
        except httpx.TimeoutException:raise HTTPException(504,'文本服务超时，未创建视频任务；可以稍后重新转换') from None
        except Exception:raise HTTPException(502,'文本服务未返回有效结果；请检查服务地址和模型配置') from None
        finally:prompt_busy.discard(user['id'])

    app.state.h3_prompt_prepare=h3_prompt
    app.state.h3_prompt_request_type=PromptRequest

    # Also support host apps that registered their catch-all StaticFiles first.
    route=next(route for route in app.router.routes if getattr(route,'endpoint',None) is h3_prompt)
    app.router.routes.remove(route)
    app.router.routes.insert(0,route)

