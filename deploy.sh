#!/bin/bash
# FastAPI Mall 部署脚本

set -e  # 遇到错误时退出

echo "🚀 开始部署 FastAPI Mall 库存微服务..."

# 检查必要工具
check_requirements() {
    echo "🔍 检查系统环境..."
    
    if ! command -v docker &> /dev/null; then
        echo "❌ 未找到 Docker，请先安装 Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo "❌ 未找到 docker-compose，请先安装 docker-compose"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        echo "❌ 未找到 Python3，请先安装 Python 3.8+"
        exit 1
    fi
    
    echo "✅ 环境检查通过"
}

# 创建环境变量文件
setup_env() {
    echo "⚙️  配置环境变量..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            echo "✅ 已创建 .env 文件，请根据需要修改配置"
        else
            echo "❌ 未找到 .env.example 模板文件"
            exit 1
        fi
    else
        echo "✅ 环境变量文件已存在"
    fi
}

# 启动基础服务
start_services() {
    echo "🐳 启动 Docker 服务..."
    
    # 启动所有服务
    docker-compose up -d
    
    # 等待服务启动
    echo "⏳ 等待服务启动..."
    sleep 10
    
    # 检查服务状态
    if docker-compose ps | grep -q "Exit"; then
        echo "❌ 有服务启动失败，请检查日志:"
        docker-compose logs
        exit 1
    fi
    
    echo "✅ 基础服务启动完成"
}

# 安装 Python 依赖
install_dependencies() {
    echo "🐍 安装 Python 依赖..."
    
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        echo "✅ Python 依赖安装完成"
    else
        echo "❌ 未找到 requirements.txt 文件"
        exit 1
    fi
}

# 数据库初始化
init_database() {
    echo "🗄️  初始化数据库..."
    
    # 等待数据库完全启动
    echo "⏳ 等待数据库就绪..."
    for i in {1..30}; do
        if docker-compose exec db pg_isready -U postgres &>/dev/null; then
            echo "✅ 数据库已就绪"
            break
        fi
        echo "⏳ 数据库启动中... ($i/30)"
        sleep 2
    done
    
    # 运行数据库迁移
    if [ -d "alembic" ]; then
        alembic upgrade head
        echo "✅ 数据库迁移完成"
    fi
}

# 启动应用
start_application() {
    echo "🏃 启动应用服务..."
    
    # 后台启动应用
    nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > app.log 2>&1 &
    APP_PID=$!
    
    # 等待应用启动
    sleep 5
    
    # 检查应用是否正常运行
    if curl -f http://localhost:8000/ &>/dev/null; then
        echo "✅ 应用启动成功"
        echo "应用查看: http://localhost:8000"
        echo "API 文档: http://localhost:8000/docs"
    else
        echo "❌ 应用启动失败，请检查 app.log"
        kill $APP_PID 2>/dev/null || true
        exit 1
    fi
}

# 显示部署信息
show_info() {
    echo ""
    echo "🎉 部署完成！"
    echo "==================="
    echo "应用查看: http://localhost:8000"
    echo "API 文档: http://localhost:8000/docs" 
    echo "pgAdmin:  http://localhost:5050"
    echo "==================="
    echo ""
    echo "📊 服务状态:"
    docker-compose ps
    echo ""
    echo "📋 常用命令:"
    echo "  停止服务: docker-compose down"
    echo "  查看日志: docker-compose logs"
    echo "  重启应用: kill $APP_PID && ./deploy.sh"
}

# 主执行流程
main() {
    check_requirements
    setup_env
    start_services
    install_dependencies
    init_database
    start_application
    show_info
}

# 执行主函数
main "$@"