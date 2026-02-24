 FastAPI Mall 部署脚本 (Windows PowerShell)

param(
    [switch]$InstallDeps = $false,
    [switch]$ResetData = $false
)

Write-Host "🚀 开始部署 FastAPI Mall 库存微服务..." -ForegroundColor Green

# 检查必要工具
function Check-Requirements {
    Write-Host "🔍 检查系统环境..." -ForegroundColor Yellow
    
    # 检查 Docker
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "❌ 未找到 Docker，请先安装 Docker Desktop" -ForegroundColor Red
        exit 1
    }
    
    # 检查 Python
    if (!(Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host "❌ 未找到 Python，请先安装 Python 3.8+" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ 环境检查通过" -ForegroundColor Green
}

# 创建环境变量文件
function Setup-Env {
    Write-Host "⚙️  配置环境变量..." -ForegroundColor Yellow
    
    if (!(Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" ".env"
            Write-Host "✅ 已创建 .env 文件，请根据需要修改配置" -ForegroundColor Green
        } else {
            Write-Host "❌ 未找到 .env.example 模板文件" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "✅ 环境变量文件已存在" -ForegroundColor Green
    }
}

# 启动基础服务
function Start-Services {
    Write-Host "🐳 启动 Docker 服务..." -ForegroundColor Yellow
    
    try {
        # 启动所有服务
        if ($ResetData) {
            docker-compose down -v
        }
        docker-compose up -d
        
        # 等待服务启动
        Write-Host "⏳ 等待服务启动..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
        
        # 检查服务状态
        $status = docker-compose ps
        if ($status -match "Exit") {
            Write-Host "❌ 有服务启动失败，请检查日志:" -ForegroundColor Red
            docker-compose logs
            exit 1
        }
        
        Write-Host "✅ 基础服务启动完成" -ForegroundColor Green
    } catch {
        Write-Host "❌ 启动服务失败: $_" -ForegroundColor Red
        exit 1
    }
}

# 安装 Python 依赖
function Install-Dependencies {
    Write-Host "🐍 安装 Python 依赖..." -ForegroundColor Yellow
    
    if (Test-Path "requirements.txt") {
        if ($InstallDeps) {
            python -m pip install --upgrade pip
        }
        pip install -r requirements.txt
        Write-Host "✅ Python 依赖安装完成" -ForegroundColor Green
    } else {
        Write-Host "❌ 未找到 requirements.txt 文件" -ForegroundColor Red
        exit 1
    }
}

# 数据库初始化
function Initialize-Database {
    Write-Host "🗄️  初始化数据库..." -ForegroundColor Yellow
    
    # 等待数据库完全启动
    Write-Host "⏳ 等待数据库就绪..." -ForegroundColor Yellow
    $retryCount = 0
    $maxRetries = 30
    
    while ($retryCount -lt $maxRetries) {
        try {
            $result = docker-compose exec db pg_isready -U postgres 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ 数据库已就绪" -ForegroundColor Green
                break
            }
        } catch {
            # 忽略错误，继续重试
        }
        
        $retryCount++
        Write-Host "⏳ 数据库启动中... ($retryCount/$maxRetries)" -ForegroundColor Yellow
        Start-Sleep -Seconds 2
    }
    
    if ($retryCount -ge $maxRetries) {
        Write-Host "❌ 数据库启动超时" -ForegroundColor Red
        exit 1
    }
    
    # 运行数据库迁移
    if (Test-Path "alembic") {
        alembic upgrade head
        Write-Host "✅ 数据库迁移完成" -ForegroundColor Green
    }
}

# 启动应用
function Start-Application {
    Write-Host "🏃 启动应用服务..." -ForegroundColor Yellow
    
    # 启动应用（后台运行）
    $process = Start-Process -FilePath "uvicorn" -ArgumentList "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -PassThru -WindowStyle Hidden
    
    # 等待应用启动
    Start-Sleep -Seconds 5
    
    # 检查应用是否正常运行
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Host "✅ 应用启动成功" -ForegroundColor Green
            Write-Host "应用查看: http://localhost:8000" -ForegroundColor Cyan
            Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
            return $process.Id
        }
    } catch {
        # 忽略错误
    }
    
    Write-Host "❌ 应用启动失败，请检查日志" -ForegroundColor Red
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    exit 1
}

# 显示部署信息
function Show-Info($AppPID) {
    Write-Host ""
    Write-Host "🎉 部署完成！" -ForegroundColor Green
    Write-Host "===================" -ForegroundColor White
    Write-Host "应用查看: http://localhost:8000" -ForegroundColor Cyan
    Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
    Write-Host "pgAdmin:  http://localhost:5050" -ForegroundColor Cyan
    Write-Host "===================" -ForegroundColor White
    Write-Host ""
    Write-Host "📊 服务状态:" -ForegroundColor Yellow
    docker-compose ps
    Write-Host ""
    Write-Host "📋 常用命令:" -ForegroundColor Magenta
    Write-Host "  停止服务: docker-compose down" -ForegroundColor White
    Write-Host "  查看日志: docker-compose logs" -ForegroundColor White
    Write-Host "  重启应用: Stop-Process -Id $AppPID -Force; .\deploy.ps1" -ForegroundColor White
}

# 主执行流程
function Main {
    Check-Requirements
    Setup-Env
    Start-Services
    Install-Dependencies
    Initialize-Database
    $appPID = Start-Application
    Show-Info -AppPID $appPID
}

# 解析命令行参数
if ($args.Count -gt 0) {
    switch ($args[0]) {
        "-h" { 
            Write-Host "使用方法: .\deploy.ps1 [-InstallDeps] [-ResetData]"
            Write-Host "  -InstallDeps : 重新安装 Python 依赖"
            Write-Host "  -ResetData   : 重置所有数据并重新部署"
            exit 0
        }
        default { 
            Write-Host "未知参数: $($args[0])，使用 -h 查看帮助"
            exit 1
        }
    }
}

# 执行主函数
Main