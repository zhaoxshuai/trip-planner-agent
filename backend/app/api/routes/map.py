"""地图相关API路由"""

from fastapi import APIRouter, Query
from typing import Optional
from ...services.amap_service import get_amap_service
from ...services.unsplash_service import get_unsplash_service
from ...models.schemas import RouteRequest
from pydantic import BaseModel

router = APIRouter(prefix="/map", tags=["map"])

# 请求模型
class GeocodeRequest(BaseModel):
    address: str
    city: Optional[str] = None

class POIDetailRequest(BaseModel):
    id: str

# 地理编码接口
@router.post("/geocode", summary="地理编码", description="将地址转换为经纬度坐标")
async def geocode(request: GeocodeRequest):
    """地理编码 - 将地址转换为经纬度坐标"""
    try:
        amap_service = get_amap_service()
        coordinates = amap_service.geocode(request.address, request.city)
        
        if coordinates:
            return {
                "success": True,
                "message": "地理编码成功",
                "data": coordinates
            }
        else:
            return {
                "success": False,
                "message": "未能获取地理编码",
                "data": None
            }
    except Exception as e:
        print(f"❌ 地理编码失败: {str(e)}")
        return {
            "success": False,
            "message": f"地理编码失败: {str(e)}",
            "data": None
        }

# POI详情接口
@router.post("/poi/detail", summary="获取POI详情", description="获取POI详细信息")
async def get_poi_detail(request: POIDetailRequest):
    """获取POI详情"""
    try:
        amap_service = get_amap_service()
        detail = amap_service.get_poi_detail(request.id)
        
        if detail:
            return {
                "success": True,
                "message": "获取POI详情成功",
                "data": detail
            }
        else:
            return {
                "success": False,
                "message": "未能获取POI详情",
                "data": None
            }
    except Exception as e:
        print(f"❌ 获取POI详情失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取POI详情失败: {str(e)}",
            "data": None
        }

# 路线规划接口
@router.post("/route/plan", summary="路线规划", description="规划两点之间的路线")
async def plan_route(request: RouteRequest):
    """路线规划 - 规划两点之间的路线"""
    try:
        amap_service = get_amap_service()
        route_info = amap_service.plan_route(
            origin_address=request.origin_address,
            destination_address=request.destination_address,
            origin_city=request.origin_city,
            destination_city=request.destination_city,
            route_type=request.route_type
        )
        
        if route_info:
            return {
                "success": True,
                "message": "路线规划成功",
                "data": route_info
            }
        else:
            return {
                "success": False,
                "message": "未能规划路线",
                "data": None
            }
    except Exception as e:
        print(f"❌ 路线规划失败: {str(e)}")
        return {
            "success": False,
            "message": f"路线规划失败: {str(e)}",
            "data": None
        }

# 获取景点图片接口
@router.get("/photo", summary="获取景点图片", description="根据景点名称从Unsplash获取图片")
async def get_attraction_photo(name: str = Query(..., description="景点名称")):
    """获取景点图片"""
    try:
        unsplash_service = get_unsplash_service()
        
        # 搜索景点图片
        photo_url = unsplash_service.get_photo_url(f"{name} China landmark")
        
        if photo_url:
            return {
                "success": True,
                "message": "获取景点图片成功",
                "data": {"photo_url": photo_url}
            }
        else:
            return {
                "success": False,
                "message": "未能获取景点图片",
                "data": None
            }
    except Exception as e:
        print(f"❌ 获取景点图片失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取景点图片失败: {str(e)}",
            "data": None
        }

# 获取天气信息接口
@router.get("/weather", summary="获取天气信息", description="获取指定城市的天气信息")
async def get_weather(city: str = Query(..., description="城市名称")):
    """获取天气信息"""
    try:
        amap_service = get_amap_service()
        weather_info = amap_service.get_weather(city)
        
        if weather_info:
            return {
                "success": True,
                "message": "获取天气信息成功",
                "data": weather_info
            }
        else:
            return {
                "success": False,
                "message": "未能获取天气信息",
                "data": None
            }
    except Exception as e:
        print(f"❌ 获取天气信息失败: {str(e)}")
        return {
            "success": False,
            "message": f"获取天气信息失败: {str(e)}",
            "data": None
        }