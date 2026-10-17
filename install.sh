#!/bin/bash
echo "[+] Atualizando pacotes..."
pkg update && pkg upgrade -y

echo "[+] Instalando Python e dependências..."
pkg install -y python git wget

echo "[+] Instalando bibliotecas Python..."
pip install requests urllib3

echo "[+] Script pronto!"
echo "[+] Execute: python ai_key_scanner.py"
