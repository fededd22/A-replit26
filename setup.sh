#!/bin/bash

GREEN='\033[1;32m'
CYAN='\033[1;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}=================================================${NC}"
echo -e "${GREEN}جاري تجهيز السيرفر  .${NC}"
echo -e "${CYAN}=================================================${NC}"

echo -e "${YELLOW}[1/4] تحديث النظام وتثبيت أدوات التشغيل الوهمي (Xvfb)...${NC}"
sudo apt update -y
sudo apt install -y python3 python3-pip xvfb wget
echo -e "${YELLOW}[2/4] تثبيت Google Chrome الرسمي...${NC}"
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt install -y ./google-chrome-stable_current_amd64.deb
rm google-chrome-stable_current_amd64.deb

echo -e "${YELLOW}[3/4] تثبيت مكتبات البايثون (Telethon & Playwright)...${NC}"
pip3 install telethon playwright

echo -e "${YELLOW}[4/4] تثبيت اعتمادات متصفح Playwright...${NC}"
python3 -m playwright install-deps

echo -e "${CYAN}=================================================${NC}"
echo -e "${GREEN}✅ اكتمل التثبيت بنجاح! السيرفر جاهز.${NC}"
echo -e "${CYAN}=================================================${NC}"

echo -e "${YELLOW}لتشغيل البوت بالخلفية، استخدم الأمر:${NC}"
echo -e "${GREEN}xvfb-run -a python3 GC.py${NC}\n"
