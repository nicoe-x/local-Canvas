"""Frame canvas @ references for H3 without changing authored dialogue or actions."""
import re

BASE=('integrated_multimodal_description','overall_soundscape','non_diegetic_music')
REF=('subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music')


def compile_prompt(text, names, seconds, style):
    for number in re.findall(r'<Picture (\d+)>',text):
        if not 1<=int(number)<=len(names):raise ValueError('参考图未连接，请先选择或连接该素材')
    matches=list(re.finditer(r'(?m)^([a-z_]+):[ \t]*',text))
    known=[m for m in matches if m[1] in BASE+REF]
    if known:
        if tuple(m[1] for m in known)==REF:return text
        if tuple(m[1] for m in known)!=BASE:
            raise ValueError('H3 模板字段不完整；可直接填写画面描述并用 @参考图 引用素材')
        if text[:known[0].start()].strip():raise ValueError('H3 模板前有多余文字')
        fields={m[1]:text[m.end():known[i+1].start() if i+1<len(known) else len(text)].strip() for i,m in enumerate(known)}
        if not all(fields.values()):raise ValueError('H3 模板字段不能为空')
        visual,sound,music=(fields[key] for key in BASE)
    else:
        visual='Visual style: '+{'写实':'live-action','二维动画':'2D animation','3D国漫':'3D Chinese animation'}.get(style,style)+'. '+text.strip()
        sound='Natural environmental and action sounds only. Speak only explicitly supplied dialogue; never read visual descriptions or technical instructions aloud.'
        music='N/A'
        visual+=' No subtitles or captions.'
    if not visual:raise ValueError('请填写画面描述')
    if '[Shot 1]' not in visual:visual='[Shot 1] '+visual
    if not names:
        return f'integrated_multimodal_description: {visual}\n\noverall_soundscape: {sound}\n\nnon_diegetic_music: {music}'
    definitions='\n'.join(f'<Subject {i}> is the visible content from <Picture {i}>. Use this reference only for the identity, appearance or environment indicated in the description. Multiple views of one person depict the same individual, not additional people.' for i in range(1,len(names)+1))
    return (f'subject_definitions: {definitions}\n\nsummary: Ref2VA, {seconds:g} seconds. Follow the supplied description and its explicit picture references.'
            '\n\nretention_analysis: Retain the identity and appearance of each referenced element only where requested. Do not reproduce reference-sheet borders, panels or neutral studio backgrounds as the story setting.'
            f'\n\ndetailed_description: {visual}\n\noverall_soundscape: {sound}\n\nnon_diegetic_music: {music}')
