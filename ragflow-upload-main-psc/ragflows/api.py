#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAGFlow public API client using one Bearer API key for every operation."""

import json
import os
import time

import requests

from ragflows import configs
from utils import fileutils, timeutils


def _api_base():
    configured = str(
        getattr(configs, 'RAGFLOW_PUBLIC_API_BASE_URL', '') or ''
    ).rstrip('/')
    if configured:
        return configured
    base = str(getattr(configs, 'OPENAI_BASE_URL', '') or '').rstrip('/')
    if '/chats_openai' in base:
        return base.rsplit('/chats_openai', 1)[0]
    if '/openai' in base:
        return base.rsplit('/openai', 1)[0]
    raise ValueError('无法推导RAGFlow公共API地址')


def _headers(content_type=True):
    token = str(getattr(configs, 'OPENAI_API_KEY', '') or '').strip()
    if not token:
        raise ValueError('OPENAI_API_KEY为空')
    if not token.lower().startswith('bearer '):
        token = f'Bearer {token}'
    result = {'Authorization': token}
    if content_type:
        result['Content-Type'] = 'application/json'
    return result


def _timeout():
    return int(getattr(configs, 'RAGFLOW_REQUEST_TIMEOUT', 180))


def _api_code(payload):
    return payload.get('code', payload.get('retcode', 0))


def is_succeed(response):
    return isinstance(response, dict) and _api_code(response) == 0


def _request_error(response, action):
    try:
        payload = response.json()
        message = payload.get('message') or payload.get('retmsg')
    except Exception:
        message = response.text[:300]
    return {
        'code': response.status_code,
        'message': f'{action}失败: {message or response.status_code}',
    }


def check_api_url() -> tuple[bool, str]:
    """Verify that the single API key can access the configured dataset."""
    try:
        response = requests.get(
            f'{_api_base()}/datasets',
            headers=_headers(),
            params={
                'id': configs.DIFY_DOC_KB_ID,
                'page': 1,
                'page_size': 10,
            },
            timeout=_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        if not is_succeed(payload):
            return False, str(payload.get('message') or payload.get('retmsg'))
        data = payload.get('data') or []
        datasets = data if isinstance(data, list) else data.get('datasets') or []
        found = any(
            str(item.get('id')) == str(configs.DIFY_DOC_KB_ID)
            for item in datasets
        )
        if not found:
            return False, 'OPENAI_API_KEY无权访问DIFY_DOC_KB_ID对应的知识库'
        timeutils.print_log('RAGFlow官方API连接正常，上传和删除使用同一身份')
        return True, 'API地址和身份配置正确'
    except Exception as exc:
        return False, f'RAGFlow官方API连接失败: {exc}'


@timeutils.monitor
def upload_file_to_kb(file_path, kb_name, kb_id, parser_id=None, run=None):
    """Upload with OPENAI_API_KEY so the same identity can later delete it."""
    url = f'{_api_base()}/datasets/{kb_id}/documents'
    try:
        with open(file_path, 'rb') as handle:
            response = requests.post(
                url,
                headers=_headers(content_type=False),
                files={
                    'file': (
                        os.path.basename(file_path),
                        handle,
                        'application/octet-stream',
                    )
                },
                data={'display_name': os.path.basename(file_path)},
                timeout=_timeout(),
            )
        if response.status_code != 200:
            return _request_error(response, '上传文档')
        payload = response.json()
        if not is_succeed(payload):
            return payload
        documents = payload.get('data') or []
        if not documents:
            return {'code': 100, 'message': '上传成功但未返回文档ID'}
        return payload
    except Exception as exc:
        return {'code': 100, 'message': f'上传文档失败: {exc}'}


@timeutils.monitor
def get_rag_list(kb_id):
    try:
        response = requests.get(
            f'{_api_base()}/datasets/{kb_id}/documents',
            headers=_headers(),
            params={'page': 1, 'page_size': 1000},
            timeout=_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        if not is_succeed(payload):
            return []
        return (payload.get('data') or {}).get('docs') or []
    except Exception as exc:
        timeutils.print_log(f'获取知识库文档列表失败: {exc}')
        return []


def get_document_by_id(doc_id, kb_id=None):
    kb_id = kb_id or configs.DIFY_DOC_KB_ID
    response = requests.get(
        f'{_api_base()}/datasets/{kb_id}/documents',
        headers=_headers(),
        params={'id': str(doc_id), 'page': 1, 'page_size': 10},
        timeout=_timeout(),
    )
    response.raise_for_status()
    payload = response.json()
    if not is_succeed(payload):
        raise RuntimeError(payload.get('message') or payload.get('retmsg'))
    documents = (payload.get('data') or {}).get('docs') or []
    return next(
        (item for item in documents if str(item.get('id')) == str(doc_id)),
        None,
    )


def get_document_by_name(filename, kb_id=None):
    kb_id = kb_id or configs.DIFY_DOC_KB_ID
    response = requests.get(
        f'{_api_base()}/datasets/{kb_id}/documents',
        headers=_headers(),
        params={'name': filename, 'page': 1, 'page_size': 100},
        timeout=_timeout(),
    )
    response.raise_for_status()
    payload = response.json()
    if not is_succeed(payload):
        message = str(payload.get('message') or payload.get('retmsg') or '')
        if "you don't own the document" in message.lower():
            # A collaborator may see a same-name document owned by another
            # account. It cannot be safely reused or deleted, so treat it as
            # absent and upload the local PDF under the current API identity.
            timeutils.print_log(
                f'知识库中存在其他账号的同名文档 {filename}，将上传当前本地文件'
            )
            return None
        raise RuntimeError(message)
    documents = (payload.get('data') or {}).get('docs') or []
    return next(
        (item for item in documents if item.get('name') == filename),
        None,
    )


def check_document_exists(filename):
    try:
        document = get_document_by_name(filename)
        return bool(document), document
    except Exception as exc:
        timeutils.print_log(f'检查文档是否存在失败: {exc}')
        return False, None


@timeutils.monitor
def parse_chunks(doc_ids, run=1):
    """Start parsing via the official API with the same OPENAI_API_KEY."""
    try:
        response = requests.post(
            f'{_api_base()}/datasets/{configs.DIFY_DOC_KB_ID}/chunks',
            headers=_headers(),
            json={'document_ids': [str(doc_id) for doc_id in doc_ids]},
            timeout=_timeout(),
        )
        if response.status_code != 200:
            return _request_error(response, '启动解析')
        return response.json()
    except Exception as exc:
        return {'code': 100, 'message': f'启动解析失败: {exc}'}


@timeutils.monitor
def parse_chunks_with_check(filename, doc_id=None):
    if not doc_id:
        document = get_document_by_name(filename)
        doc_id = (document or {}).get('id')
    if not doc_id:
        timeutils.print_log(f'找不到文档ID，无法解析: {filename}')
        return False

    result = parse_chunks([doc_id], run=1)
    if not is_succeed(result):
        timeutils.print_log(
            f'启动解析失败: {result.get("message") or result.get("retmsg")}'
        )
        return False

    interval = float(getattr(configs, 'PROGRESS_CHECK_INTERVAL', 1))
    max_wait = int(getattr(configs, 'PARSE_MAX_WAIT_SECONDS', 1800))
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        document = get_document_by_id(doc_id)
        if not document:
            timeutils.print_log(f'解析期间文档消失: {doc_id}')
            return False

        progress = float(document.get('progress') or 0)
        run_state = str(document.get('run') or '').upper()
        if getattr(configs, 'ENABLE_PROGRESS_LOG', True):
            timeutils.print_log(f'{filename}解析进度为：{progress * 100:.2f}%')
        if progress >= 1 or run_state == 'DONE':
            return True
        if progress < 0 or run_state in {'FAIL', 'CANCEL'}:
            message = f'[{filename}]解析失败，progress={progress}, run={run_state}'
            timeutils.print_log(message)
            fileutils.save(
                f'{fileutils.get_cache_dir()}/ragflow_fail.txt',
                f'{timeutils.get_now_str()} {message}\n',
            )
            return False
        time.sleep(interval)

    timeutils.print_log(f'解析等待超时: {filename}, doc_id={doc_id}')
    return False


def set_document_metadata(doc_id, filepath) -> bool:
    """Metadata is optional and disabled by default."""
    if not getattr(configs, 'METADATA_SUFFIX', ''):
        return False
    timeutils.print_log('官方API模式暂不自动写入自定义metadata，已跳过')
    return False
