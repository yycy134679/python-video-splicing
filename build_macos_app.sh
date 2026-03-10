#!/bin/bash
# ================================================================
# 视频拼接工具 macOS 应用打包脚本
#
# 打包流程：
#   1. PyInstaller 执行 COLLECT → 生成 dist/VideoSplicer/
#   2. 手动组装 .app 目录结构（比 PyInstaller BUNDLE 更可靠）
#   3. 可选：生成 DMG 安装包
#
# 打包者需要：Homebrew + FFmpeg + Python
# 使用者无需安装任何依赖，双击即用
# ================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

APP_NAME="视频拼接工具"
APP_VERSION="2.1"
BUNDLE_ID="com.bytedance.video-splicer"
APP_DIR="dist/${APP_NAME}.app"
ZIP_PATH="dist/${APP_NAME}-v${APP_VERSION}.zip"
BUILD_DMG="${BUILD_DMG:-0}"

echo "🚀 开始打包 macOS 应用..."
echo ""

# ---- 1. 环境检查 ----
echo -e "${YELLOW}▶ 检查环境...${NC}"

python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Python: $python_version"

if ! command -v ffmpeg &> /dev/null; then
    echo -e "${RED}   ✗ FFmpeg 未安装，请运行: brew install ffmpeg${NC}"
    exit 1
fi
echo "   FFmpeg: $(which ffmpeg)"
echo "   FFprobe: $(which ffprobe)"

# ---- 2. 激活现有虚拟环境 ----
if [ ! -d ".venv" ]; then
    echo -e "${RED}   ✗ .venv 不存在，请先创建虚拟环境${NC}"
    exit 1
fi

echo -e "${YELLOW}▶ 激活虚拟环境 & 安装依赖...${NC}"
source .venv/bin/activate

pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q pyinstaller

# ---- 3. 清理旧构建 ----
echo -e "${YELLOW}▶ 清理旧构建...${NC}"
rm -rf build dist

# ---- 4. PyInstaller（仅 COLLECT，不做 BUNDLE）----
echo -e "${YELLOW}▶ PyInstaller 打包中（可能需要几分钟）...${NC}"
pyinstaller video_splicing.spec --clean --noconfirm

# 验证 COLLECT 产物
if [ ! -f "dist/VideoSplicer/VideoSplicer" ]; then
    echo -e "${RED}✗ PyInstaller COLLECT 失败，请检查上方错误信息${NC}"
    deactivate
    exit 1
fi
echo -e "${GREEN}   ✓ PyInstaller COLLECT 完成${NC}"

# ---- 5. 手动创建 .app 结构 ----
echo -e "${YELLOW}▶ 创建 .app 应用包...${NC}"

rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# 5a. 写入 Info.plist
cat > "$APP_DIR/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>launcher</string>
    <key>CFBundleIdentifier</key>
    <string>${BUNDLE_ID}</string>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleVersion</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleIconFile</key>
    <string>icon</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
</dict>
</plist>
PLIST

# 5b. 写入启动器脚本（macOS 运行 .app 时执行的入口）
cat > "$APP_DIR/Contents/MacOS/launcher" << 'LAUNCHER'
#!/bin/bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/Resources"
LOG_DIR="$HOME/Library/Logs/video-splicer"
mkdir -p "$LOG_DIR"
nohup "$DIR/VideoSplicer/VideoSplicer" "$@" >> "$LOG_DIR/launcher.log" 2>&1 &
exit 0
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/launcher"

# 5c. 将 PyInstaller 输出复制到 Resources
cp -R dist/VideoSplicer "$APP_DIR/Contents/Resources/"

# 5d. 复制自定义图标（如果存在）
if [ -f "icon.icns" ]; then
    cp icon.icns "$APP_DIR/Contents/Resources/"
    echo "   ✓ 已添加自定义图标"
fi

echo -e "${GREEN}   ✓ .app 创建完成${NC}"

# ---- 6. 验证关键文件 ----
echo -e "${YELLOW}▶ 验证打包结果...${NC}"

exe_path="$APP_DIR/Contents/Resources/VideoSplicer/VideoSplicer"
internal="$APP_DIR/Contents/Resources/VideoSplicer/_internal"

check_file() {
    if [ -e "$1" ]; then
        echo -e "   ${GREEN}✓${NC} $2"
    else
        echo -e "   ${RED}✗ $2 缺失${NC}"
    fi
}

check_file "$exe_path"            "主程序 (VideoSplicer)"
check_file "$internal/ffmpeg"     "FFmpeg"
check_file "$internal/ffprobe"    "FFprobe"
check_file "$internal/app.py"     "app.py"
check_file "$internal/video_splicer" "video_splicer/"
check_file "$internal/assets/video/endcard.mp4" "落版视频 (endcard.mp4)"

app_size=$(du -sh "$APP_DIR" | awk '{print $1}')
echo "   📦 应用大小: $app_size"

# ---- 7. 创建 ZIP 分发包 ----
echo -e "${YELLOW}▶ 创建 ZIP 分发包...${NC}"
rm -f "$ZIP_PATH"
ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$ZIP_PATH"
echo -e "${GREEN}   ✓ ZIP: $(pwd)/$ZIP_PATH${NC}"

# ---- 8. 可选：创建 DMG ----
if [[ "$BUILD_DMG" == "1" ]]; then
    dmg_name="${APP_NAME}-v${APP_VERSION}.dmg"
    echo -e "${YELLOW}▶ 创建 DMG...${NC}"
    rm -f "$dmg_name"
    hdiutil create -volname "$APP_NAME" \
                   -srcfolder "$APP_DIR" \
                   -ov -format UDZO \
                   "$dmg_name"
    echo -e "${GREEN}   ✓ DMG: $(pwd)/$dmg_name${NC}"
fi

# ---- 完成 ----
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  打包成功！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "📦 应用位置: $(pwd)/dist/${APP_NAME}.app"
echo ""
echo "🗜️ ZIP 位置: $(pwd)/$ZIP_PATH"
echo ""
echo "🚀 测试运行:"
echo "   open \"dist/${APP_NAME}.app\""
echo ""
echo "✅ 同事无需安装 Homebrew/FFmpeg/Python，双击即用！"

deactivate 2>/dev/null || true
