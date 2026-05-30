"""天气查询技能——mock 实现"""
def execute(params: dict) -> dict:
    city = params.get('city', '北京')
    return {'city': city, 'temperature': '22°C', 'condition': '晴', 'humidity': '45%', 'tip': f'{city}今天晴，22°C，适合户外活动'}
