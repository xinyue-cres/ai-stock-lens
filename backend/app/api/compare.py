"""多股横向对比 AI 分析 API。"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.analyzer import analyze_compare
from app.ai.client import get_model_name
from app.db import get_session
from app.indicators.engine import compute_all
from app.models.ai_report import AIReport
from app.models.stock import Stock
from app.services.analysis_service import load_kline_df

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    codes: list[str]
    force: bool = False


def _build_stock_snapshot(session: Session, code: str, model: str) -> tuple[dict, pd.DataFrame] | None:
    """为单只票构建对比分析所需的快照 + 原始 K 线 DataFrame。"""
    stock = session.get(Stock, code)
    if not stock:
        return None

    df = load_kline_df(session, code)
    if df.empty:
        return None

    indicators = compute_all(df)
    latest = indicators.get("latest_price", {}) or {}
    ma = indicators.get("ma", {}) or {}
    boll = indicators.get("boll", {}) or {}

    report = session.exec(
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == "combined")
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    ).first()

    extras: dict = {}
    if report and report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            extras = {}

    scenarios = extras.get("scenarios", [])
    best_entry = None
    close = latest.get("close")
    if close and scenarios:
        for sc in scenarios:
            if sc.get("scenario_type") in ("entry", "add"):
                conds = sc.get("conditions") or []
                for c in conds:
                    if c.get("kind") == "price" and c.get("value"):
                        dist = abs(c["value"] - close) / close
                        if best_entry is None or dist < best_entry["distance_pct"]:
                            best_entry = {"price": c["value"], "distance_pct": round(dist * 100, 2)}

    risk_reward = None
    if scenarios:
        for sc in scenarios:
            rr = sc.get("risk_reward")
            if rr and isinstance(rr, str) and ":" in rr:
                try:
                    parts = rr.split(":")
                    risk_reward = round(float(parts[1]) / float(parts[0]), 2)
                except (ValueError, IndexError, ZeroDivisionError):
                    pass
                if risk_reward:
                    break

    snap = {
        "code": code,
        "name": stock.name or code,
        "close": close,
        "pct_chg": latest.get("pct_chg"),
        "turnover": latest.get("turnover"),
        "ma5": ma.get("ma5"),
        "ma10": ma.get("ma10"),
        "ma20": ma.get("ma20"),
        "ma60": ma.get("ma60"),
        "atr": indicators.get("atr", {}).get("atr") if isinstance(indicators.get("atr"), dict) else None,
        "boll_upper": boll.get("upper"),
        "boll_lower": boll.get("lower"),
        "verdict": report.verdict if report else None,
        "confidence": report.confidence if report else None,
        "summary": report.summary if report else None,
        "key_signals": extras.get("key_signals", []),
        "scenarios": scenarios,
        "best_entry_distance": best_entry,
        "best_risk_reward": risk_reward,
    }
    return snap, df


def _compute_cross_stock_metrics(snapshots: list[dict], dfs: dict[str, pd.DataFrame]) -> dict:
    """计算跨票指标：相关性矩阵、超额收益、组合波动率。"""
    codes = [s["code"] for s in snapshots]
    n = len(codes)

    # 对齐日期取近 60 日收益率
    returns_map: dict[str, pd.Series] = {}
    for code in codes:
        df = dfs[code]
        if "pct_chg" in df.columns and len(df) >= 20:
            ret = df["pct_chg"].tail(60).reset_index(drop=True)
            returns_map[code] = ret

    # 相关性矩阵
    correlation_matrix: list[dict] = []
    if len(returns_map) >= 2:
        ret_df = pd.DataFrame(returns_map)
        corr = ret_df.corr()
        for i in range(n):
            for j in range(i + 1, n):
                ci, cj = codes[i], codes[j]
                if ci in corr.columns and cj in corr.columns:
                    val = corr.loc[ci, cj]
                    if not np.isnan(val):
                        ni = next(s["name"] for s in snapshots if s["code"] == ci)
                        nj = next(s["name"] for s in snapshots if s["code"] == cj)
                        correlation_matrix.append({
                            "pair": f"{ni} vs {nj}",
                            "corr": round(float(val), 3),
                            "desc": "高度同步" if val > 0.7 else "中度相关" if val > 0.4 else "低相关" if val > 0 else "负相关",
                        })

    # 超额收益（相对等权平均）
    excess_returns: list[dict] = []
    if len(returns_map) >= 2:
        ret_df = pd.DataFrame(returns_map).dropna()
        if not ret_df.empty:
            cum = (1 + ret_df / 100).prod() - 1
            avg_ret = cum.mean()
            for code in codes:
                if code in cum.index:
                    name = next(s["name"] for s in snapshots if s["code"] == code)
                    excess = float(cum[code] - avg_ret)
                    excess_returns.append({
                        "code": code,
                        "name": name,
                        "cum_return_60d": round(float(cum[code]) * 100, 2),
                        "excess_vs_avg": round(excess * 100, 2),
                    })
            excess_returns.sort(key=lambda x: x["excess_vs_avg"], reverse=True)

    # 组合波动率 vs 等权平均
    portfolio_vol_note = ""
    if len(returns_map) >= 2:
        ret_df = pd.DataFrame(returns_map).dropna()
        if len(ret_df) >= 10:
            individual_vols = (ret_df / 100).std()
            avg_vol = float(individual_vols.mean())
            portfolio_vol = float((ret_df.sum(axis=1) / (n * 100)).std())
            diversification_ratio = round(portfolio_vol / avg_vol, 2) if avg_vol > 0 else 1.0
            if diversification_ratio < 0.7:
                portfolio_vol_note = f"组合波动率仅为个股平均的{diversification_ratio:.0%}，分散效果显著"
            elif diversification_ratio < 0.9:
                portfolio_vol_note = f"组合波动率为个股平均的{diversification_ratio:.0%}，有一定分散效果"
            else:
                portfolio_vol_note = f"组合波动率为个股平均的{diversification_ratio:.0%}，分散效果有限（同质化）"

    return {
        "correlation_matrix": correlation_matrix,
        "excess_returns": excess_returns,
        "portfolio_vol_note": portfolio_vol_note,
    }


@router.post("")
def generate_compare(payload: CompareRequest, session: Session = Depends(get_session)):
    if len(payload.codes) < 2:
        raise HTTPException(400, "至少选择 2 只股票")
    if len(payload.codes) > 6:
        raise HTTPException(400, "最多选择 6 只股票")

    codes_sorted = sorted(payload.codes)
    code_key = ",".join(codes_sorted)
    model = get_model_name()
    today = date.today()

    # 检查缓存
    if not payload.force:
        cached = session.exec(
            select(AIReport)
            .where(
                AIReport.code == code_key,
                AIReport.model == model,
                AIReport.horizon == "compare",
                AIReport.as_of_date == today,
            )
            .order_by(AIReport.created_at.desc())
            .limit(1)
        ).first()
        if cached:
            extras = {}
            if cached.extras_json:
                try:
                    extras = json.loads(cached.extras_json)
                except json.JSONDecodeError:
                    pass
            return {
                "id": cached.id,
                "codes": codes_sorted,
                "as_of_date": str(cached.as_of_date),
                "summary": cached.summary,
                "report_md": cached.report_md,
                "cached": True,
                **extras,
            }

    # 构建各票快照
    stocks_data = []
    kline_dfs: dict[str, pd.DataFrame] = {}
    for code in codes_sorted:
        result = _build_stock_snapshot(session, code, model)
        if result:
            snap, df = result
            stocks_data.append(snap)
            kline_dfs[code] = df

    if len(stocks_data) < 2:
        raise HTTPException(400, "可分析的股票不足 2 只（部分无数据）")

    # 计算跨票指标（单票分析中不存在的新信息）
    cross_metrics = _compute_cross_stock_metrics(stocks_data, kline_dfs)

    # 调用 AI（传入跨票指标）
    result = analyze_compare(stocks_data, cross_metrics)

    # 存储
    report = AIReport(
        code=code_key,
        as_of_date=today,
        model=model,
        horizon="compare",
        report_md=result.get("report_md", ""),
        verdict="neutral",
        summary=result.get("summary", ""),
        extras_json=json.dumps({
            "ranking": result.get("ranking", []),
            "allocation": result.get("allocation", []),
            "correlation_note": result.get("correlation_note", ""),
            "risk_note": result.get("risk_note", ""),
        }, ensure_ascii=False),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return {
        "id": report.id,
        "codes": codes_sorted,
        "as_of_date": str(today),
        "summary": result.get("summary"),
        "report_md": result.get("report_md"),
        "ranking": result.get("ranking", []),
        "allocation": result.get("allocation", []),
        "correlation_note": result.get("correlation_note", ""),
        "risk_note": result.get("risk_note", ""),
        "cached": False,
    }


@router.get("/history")
def compare_history(session: Session = Depends(get_session)):
    model = get_model_name()
    reports = session.exec(
        select(AIReport)
        .where(AIReport.model == model, AIReport.horizon == "compare")
        .order_by(AIReport.created_at.desc())
        .limit(50)
    )
    items = []
    for r in reports:
        codes = r.code.split(",")
        # 取名字
        names = []
        for c in codes:
            s = session.get(Stock, c)
            names.append(s.name if s else c)
        items.append({
            "id": r.id,
            "codes": codes,
            "names": names,
            "as_of_date": str(r.as_of_date),
            "summary": r.summary,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        })
    return {"items": items}


@router.get("/{report_id}")
def compare_detail(report_id: int, session: Session = Depends(get_session)):
    report = session.get(AIReport, report_id)
    if not report or report.horizon != "compare":
        raise HTTPException(404, "对比报告不存在")

    extras: dict = {}
    if report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            pass

    codes = report.code.split(",")
    names = []
    for c in codes:
        s = session.get(Stock, c)
        names.append(s.name if s else c)

    return {
        "id": report.id,
        "codes": codes,
        "names": names,
        "as_of_date": str(report.as_of_date),
        "summary": report.summary,
        "report_md": report.report_md,
        "created_at": report.created_at.strftime("%Y-%m-%d %H:%M"),
        **extras,
    }


@router.delete("/{report_id}")
def delete_compare(report_id: int, session: Session = Depends(get_session)):
    report = session.get(AIReport, report_id)
    if not report or report.horizon != "compare":
        raise HTTPException(404, "对比报告不存在")
    session.delete(report)
    session.commit()
    return {"ok": True}
