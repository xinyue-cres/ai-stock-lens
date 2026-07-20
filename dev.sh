#!/bin/bash
# AI Stock Lens — 本地开发一键启动脚本
# 用法: ./dev.sh [start|stop|restart|status]

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PID_FILE="$ROOT_DIR/.backend.pid"
FRONTEND_PID_FILE="$ROOT_DIR/.frontend.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $1"; }

is_running() {
  local pid_file="$1"
  if [ -f "$pid_file" ]; then
    local pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    rm -f "$pid_file"
  fi
  return 1
}

start_backend() {
  if is_running "$BACKEND_PID_FILE"; then
    log_warn "后端已在运行 (PID: $(cat $BACKEND_PID_FILE))"
    return
  fi
  log_info "启动后端..."
  cd "$BACKEND_DIR"
  if [ ! -d ".venv" ]; then
    log_err "未找到 .venv，请先运行: cd backend && python -m venv .venv && pip install -e ."
    return 1
  fi
  source .venv/bin/activate
  nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$ROOT_DIR/.backend.log" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
  sleep 1
  if is_running "$BACKEND_PID_FILE"; then
    log_ok "后端启动成功 (PID: $(cat $BACKEND_PID_FILE)) → http://localhost:8000"
  else
    log_err "后端启动失败，查看日志: .backend.log"
    cat "$ROOT_DIR/.backend.log" | tail -10
  fi
}

start_frontend() {
  if is_running "$FRONTEND_PID_FILE"; then
    log_warn "前端已在运行 (PID: $(cat $FRONTEND_PID_FILE))"
    return
  fi
  log_info "启动前端..."
  cd "$FRONTEND_DIR"
  if [ ! -d "node_modules" ]; then
    log_info "安装前端依赖..."
    pnpm install
  fi
  nohup pnpm dev > "$ROOT_DIR/.frontend.log" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
  sleep 2
  if is_running "$FRONTEND_PID_FILE"; then
    log_ok "前端启动成功 (PID: $(cat $FRONTEND_PID_FILE)) → http://localhost:5173"
  else
    log_err "前端启动失败，查看日志: .frontend.log"
    cat "$ROOT_DIR/.frontend.log" | tail -10
  fi
}

stop_backend() {
  if is_running "$BACKEND_PID_FILE"; then
    local pid=$(cat "$BACKEND_PID_FILE")
    kill "$pid" 2>/dev/null
    rm -f "$BACKEND_PID_FILE"
    log_ok "后端已停止 (PID: $pid)"
  else
    log_warn "后端未在运行"
  fi
}

stop_frontend() {
  if is_running "$FRONTEND_PID_FILE"; then
    local pid=$(cat "$FRONTEND_PID_FILE")
    kill "$pid" 2>/dev/null
    rm -f "$FRONTEND_PID_FILE"
    log_ok "前端已停止 (PID: $pid)"
  else
    log_warn "前端未在运行"
  fi
}

show_status() {
  echo ""
  if is_running "$BACKEND_PID_FILE"; then
    log_ok "后端: 运行中 (PID: $(cat $BACKEND_PID_FILE)) → http://localhost:8000"
  else
    log_warn "后端: 未运行"
  fi
  if is_running "$FRONTEND_PID_FILE"; then
    log_ok "前端: 运行中 (PID: $(cat $FRONTEND_PID_FILE)) → http://localhost:5173"
  else
    log_warn "前端: 未运行"
  fi
  echo ""
}

show_menu() {
  echo ""
  echo -e "${CYAN}═══════════════════════════════════════${NC}"
  echo -e "${CYAN}       AI Stock Lens · 开发控制台      ${NC}"
  echo -e "${CYAN}═══════════════════════════════════════${NC}"
  echo ""
  show_status
  echo "  1) 启动全部 (后端+前端)"
  echo "  2) 仅启动后端"
  echo "  3) 仅启动前端"
  echo "  4) 停止全部"
  echo "  5) 重启全部"
  echo "  6) 查看后端日志"
  echo "  7) 查看前端日志"
  echo "  8) 状态"
  echo "  0) 退出"
  echo ""
  echo -n "  请选择 [0-8]: "
}

interactive() {
  while true; do
    show_menu
    read -r choice
    echo ""
    case "$choice" in
      1) start_backend; start_frontend ;;
      2) start_backend ;;
      3) start_frontend ;;
      4) stop_backend; stop_frontend ;;
      5) stop_backend; stop_frontend; sleep 1; start_backend; start_frontend ;;
      6) tail -30 "$ROOT_DIR/.backend.log" 2>/dev/null || log_warn "无后端日志" ;;
      7) tail -30 "$ROOT_DIR/.frontend.log" 2>/dev/null || log_warn "无前端日志" ;;
      8) show_status ;;
      0) echo "再见!"; exit 0 ;;
      *) log_err "无效选项" ;;
    esac
    echo ""
    echo -n "  按回车继续..."
    read -r
  done
}

# 命令行直接调用模式
case "${1:-}" in
  start)   start_backend; start_frontend ;;
  stop)    stop_backend; stop_frontend ;;
  restart) stop_backend; stop_frontend; sleep 1; start_backend; start_frontend ;;
  status)  show_status ;;
  "")      interactive ;;
  *)       echo "用法: $0 [start|stop|restart|status]"; exit 1 ;;
esac
