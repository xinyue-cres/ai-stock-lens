"""Datasource package. 对外唯一入口：get_data_router()。"""
from app.datasource.router import DataRouter, get_data_router

__all__ = ["DataRouter", "get_data_router"]
