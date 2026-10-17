#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI API Key Scanner - Termux/Kali NetHunter
Varre GitHub e valida chaves API de IAs
"""

import re
import requests
import json
import time
import base64
from typing import List, Optional
from dataclasses import dataclass
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class APIKey:
    key: str
    provider: str
    source_url: str
    is_valid: bool = False
    error_msg: str = ""


class AIKeyScanner:
    KEY_PATTERNS = {
        'openai': r'\b(sk-[a-zA-Z0-9]{48,50}|sk-proj-[a-zA-Z0-9]{20,60})\b',
        'deepseek': r'\b(sk-[a-f0-9]{32})\b',
        'anthropic': r'\b(sk-ant-[a-zA-Z0-9_-]{40,110})\b',
        'gemini': r'\b(AIzaSy[a-zA-Z0-9_-]{33,39})\b',
        'huggingface': r'\b(hf_[a-zA-Z0-9]{30,40})\b',
        'replicate': r'\b(r8_[a-zA-Z0-9]{30,40})\b',
        'mistral': r'\b(mistral-[a-zA-Z0-9]{30,40})\b',
        'groq': r'\b(gsk_[a-zA-Z0-9]{30,50})\b',
        'cohere': r'\b(cohere-[a-zA-Z0-9]{30,40})\b',
    }

    VALIDATION_ENDPOINTS = {
        'openai': {
            'url': 'https://api.openai.com/v1/models',
            'headers': lambda k: {'Authorization': f'Bearer {k}'},
            'valid_response': 200,
        },
        'deepseek': {
            'url': 'https://api.deepseek.com/v1/models',
            'headers': lambda k: {'Authorization': f'Bearer {k}'},
            'valid_response': 200,
        },
        'anthropic': {
            'url': 'https://api.anthropic.com/v1/models',
            'headers': lambda k: {'x-api-key': k, 'anthropic-version': '2023-06-01'},
            'valid_response': 200,
        },
        'huggingface': {
            'url': 'https://huggingface.co/api/whoami-v2',
            'headers': lambda k: {'Authorization': f'Bearer {k}'},
            'valid_response': 200,
        },
        'mistral': {
            'url': 'https://api.mistral.ai/v1/models',
            'headers': lambda k: {'Authorization': f'Bearer {k}'},
            'valid_response': 200,
        },
        'groq': {
            'url': 'https://api.groq.com/openai/v1/models',
            'headers': lambda k: {'Authorization': f'Bearer {k}'},
            'valid_response': 200,
        },
        'gemini': {
            'url': 'https://generativelanguage.googleapis.com/v1beta/models',
            'headers': lambda k: {'x-goog-api-key': k},
            'valid_response': 200,
        },
    }

    def __init__(self, github_token: Optional[str] = None, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'
        })
        if github_token:
            self.session.headers['Authorization'] = f'token {github_token}'

        self.found_keys: List[APIKey] = []
        self.valid_keys: List[APIKey] = []

    def _decode_base64(self, content: str) -> str:
        try:
            return base64.b64decode(content).decode('utf-8', errors='ignore')
        except Exception:
            return content

    def _key_exists(self, key: str) -> bool:
        return any(k.key == key for k in self.found_keys)

    def _extract_keys(self, content: str, source_url: str) -> List[APIKey]:
        keys_found = []
        for provider, pattern in self.KEY_PATTERNS.items():
            matches = re.findall(pattern, content)
            for match in matches:
                if self._key_exists(match):
                    continue
                key = APIKey(key=match, provider=provider, source_url=source_url)
                keys_found.append(key)
                self.found_keys.append(key)
                print(f"   [OK] [{provider.upper():12}] {match[:25]}...")
        return keys_found

    def search_github(self, query: str, per_page: int = 30, max_pages: int = 3) -> List[APIKey]:
        print(f"\n[+] Buscando no GitHub: {query}")
        search_url = 'https://api.github.com/search/code'

        for page in range(1, max_pages + 1):
            params = {'q': query, 'per_page': per_page, 'page': page}
            try:
                response = self.session.get(search_url, params=params, timeout=self.timeout)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    print(f"   [{page}] {len(items)} resultados ({data.get('total_count', 0)} total)")

                    for item in items:
                        file_url = item.get('git_url', '')
                        if not file_url:
                            continue
                        try:
                            file_response = self.session.get(file_url, timeout=self.timeout)
                            if file_response.status_code == 200:
                                content = file_response.json().get('content', '')
                                decoded = self._decode_base64(content)
                                self._extract_keys(decoded, item.get('html_url', ''))
                        except Exception:
                            continue

                elif response.status_code == 403:
                    print("   [!] Rate limit, aguardando 60s...")
                    time.sleep(60)
                    continue
                else:
                    print(f"   [!] Status {response.status_code} (token GitHub necessario para code search)")
                    break

            except Exception as e:
                print(f"   [!] Erro: {e}")
                break

            time.sleep(0.5)

        return self.found_keys

    def scan_text(self, text: str, source_url: str = 'manual-input') -> List[APIKey]:
        """Busca chaves em qualquer texto colado (util no Termux)"""
        print(f"\n[+] Analisando texto de: {source_url}")
        return self._extract_keys(text, source_url)

    def validate_key(self, api_key: APIKey) -> bool:
        provider = api_key.provider
        if provider not in self.VALIDATION_ENDPOINTS:
            api_key.error_msg = "Sem endpoint de validacao"
            return False

        endpoint = self.VALIDATION_ENDPOINTS[provider]
        try:
            response = self.session.get(
                endpoint['url'],
                headers=endpoint['headers'](api_key.key),
                timeout=self.timeout,
                verify=False
            )
            if response.status_code == endpoint['valid_response']:
                api_key.is_valid = True
                self.valid_keys.append(api_key)
                return True
            api_key.error_msg = f"Status {response.status_code}"
            return False
        except Exception as e:
            api_key.error_msg = str(e)[:60]
            return False

    def validate_all_keys(self, delay: float = 2.0) -> int:
        print(f"\n[+] Validando {len(self.found_keys)} chaves...")
        valid_count = 0
        for i, key in enumerate(self.found_keys, 1):
            print(f"\n[{i}/{len(self.found_keys)}] [{key.provider.upper()}] {key.key[:20]}...")
            if self.validate_key(key):
                print("   [OK] VALIDA!")
                valid_count += 1
            else:
                print(f"   [!] Invalida: {key.error_msg}")
            time.sleep(delay)
        return valid_count

    def save_results(self, filename: str = 'api_keys.json'):
        results = {
            'found_keys': [
                {'key': k.key, 'provider': k.provider, 'source': k.source_url,
                 'valid': k.is_valid, 'error': k.error_msg}
                for k in self.found_keys
            ],
            'summary': {
                'total_found': len(self.found_keys),
                'total_valid': len(self.valid_keys)
            }
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[+] Resultados salvos: {filename}")

    def print_summary(self):
        print("\n" + "=" * 60)
        print("RESUMO")
        print("=" * 60)
        print(f"Total encontrado: {len(self.found_keys)}")
        print(f"Validas: {len(self.valid_keys)}")
        if self.valid_keys:
            print("\n[+] CHAVES VALIDAS:")
            for key in self.valid_keys:
                print(f"  [{key.provider.upper():12}] {key.key[:30]}...")
                print(f"    Fonte: {key.source_url}")
        print("=" * 60)


def main():
    print("=" * 60)
    print("AI API KEY SCANNER - Termux/Kali NetHunter")
    print("=" * 60)

    GITHUB_TOKEN = ""  # Opcional: "ghp_..." para busca de codigo no GitHub
    scanner = AIKeyScanner(github_token=GITHUB_TOKEN if GITHUB_TOKEN else None)

    print("\n[1] Buscar no GitHub")
    print("[2] Analisar texto/colar conteudo (.env, config, etc)")
    print("[3] Analisar arquivo local")
    choice = input("Escolha [1/2/3]: ").strip()

    if choice == '1':
        queries = [
            'deepseek_api_key',
            'openai_api_key',
            'anthropic_api_key',
            'gemini_api_key',
            'groq_api_key',
        ]
        for q in queries:
            scanner.search_github(q, per_page=30, max_pages=3)

    elif choice == '2':
        print("Cole o conteudo abaixo (Ctrl+D / Enter duplo para finalizar):")
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        scanner.scan_text("\n".join(lines))

    elif choice == '3':
        path = input("Caminho do arquivo: ").strip()
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                scanner.scan_text(f.read(), source_url=path)
        except Exception as e:
            print(f"[!] Erro ao ler arquivo: {e}")
            return

    if scanner.found_keys:
        scanner.validate_all_keys(delay=2.0)
    else:
        print("\n[!] Nenhuma chave encontrada.")

    scanner.save_results()
    scanner.print_summary()


if __name__ == '__main__':
    main()
