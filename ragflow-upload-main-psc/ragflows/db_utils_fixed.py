#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Delete RAGFlow documents through its public API, never through MySQL."""

import time

import requests

from ragflows import configs
from utils import timeutils


def _get_public_api_base():
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


def _get_public_api_headers():
    token = str(getattr(configs, 'OPENAI_API_KEY', '') or '').strip()
    if not token:
        raise ValueError('OPENAI_API_KEY为空')
    if not token.lower().startswith('bearer '):
        token = f'Bearer {token}'
    return {'Authorization': token, 'Content-Type': 'application/json'}


def _api_code(payload):
    return payload.get('code', payload.get('retcode', 0))


def _means_document_is_missing(message):
    """RAGFlow v0.20 reports a deleted document as "don't own"."""
    normalized = str(message or '').strip().lower()
    missing_markers = (
        "you don't own the document",
        "dataset doesn't own the document",
        'dataset does not own the document',
        'dataset not own the document',
        'document not found',
        'document does not exist',
        'not found',
        'not exist',
        '不存在',
        '未找到',
    )
    return any(marker in normalized for marker in missing_markers)


def _document_still_exists(url, headers, doc_id, timeout):
    response = requests.get(
        url,
        headers=headers,
        params={'id': str(doc_id), 'page': 1, 'page_size': 10},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    code = _api_code(payload)
    if code not in (0, None):
        message = payload.get('message') or payload.get('retmsg') or ''
        # DELETE already returned code=0. In RAGFlow v0.20, querying the
        # deleted ID returns code=102 with "You don't own the document".
        # That response means the document is gone, not that DELETE failed.
        if _means_document_is_missing(message):
            return False
        raise RuntimeError(
            message or f'文档删除验证失败，code={code}'
        )
    documents = (payload.get('data') or {}).get('docs') or []
    return any(str(item.get('id')) == str(doc_id) for item in documents)


def _chunks_still_exist(base_url, dataset_id, headers, doc_id, timeout):
    response = requests.get(
        f'{base_url}/datasets/{dataset_id}/documents/{doc_id}/chunks',
        headers=headers,
        params={'page': 1, 'page_size': 1},
        timeout=timeout,
    )
    if response.status_code == 404:
        return False
    response.raise_for_status()
    payload = response.json()
    code = _api_code(payload)
    if code not in (0, None):
        message = str(payload.get('message') or payload.get('retmsg') or '')
        if _means_document_is_missing(message):
            return False
        raise RuntimeError(message or f'切片删除验证失败，code={code}')
    return bool((payload.get('data') or {}).get('chunks') or [])


def delete_document_group(documents):
    """Delete one or two source documents, then verify documents and chunks.

    Listing by dataset (rather than by a missing ID) makes retry after a
    partial deletion safe. Never accept a failed DELETE as proof of deletion.
    """
    try:
        ids = [str(document['id']) for document in documents]
        if len(ids) not in (1, 2) or len(set(ids)) != len(ids):
            raise ValueError('文献组删除必须提供一到两个不同的文档ID')
        dataset_id = str(configs.DIFY_DOC_KB_ID)
        base = _get_public_api_base()
        url = f'{base}/datasets/{dataset_id}/documents'
        headers = _get_public_api_headers()
        timeout = int(getattr(configs, 'RAGFLOW_REQUEST_TIMEOUT', 180))
        existing = set()
        page = 1
        while True:
            response = requests.get(url, headers=headers,
                                    params={'page': page, 'page_size': 100}, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if _api_code(payload) not in (0, None):
                raise RuntimeError(payload.get('message') or '删除前文档列表查询失败')
            data = payload.get('data') or {}
            docs = data.get('docs') or []
            existing.update(str(doc['id']) for doc in docs)
            if not docs or len(docs) < 100:
                break
            page += 1
        remaining = [doc_id for doc_id in ids if doc_id in existing]
        if remaining:
            response = requests.delete(url, headers=headers, json={'ids': remaining}, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if _api_code(payload) not in (0, None):
                raise RuntimeError(payload.get('message') or '文献组删除失败')
        retries = int(getattr(configs, 'DOCUMENT_DELETE_VERIFY_RETRIES', 15))
        interval = float(getattr(configs, 'DOCUMENT_DELETE_VERIFY_INTERVAL', 1))
        for attempt in range(retries + 1):
            cleared = True
            for doc_id in ids:
                if _document_still_exists(url, headers, doc_id, timeout):
                    cleared = False
                if _chunks_still_exist(base, dataset_id, headers, doc_id, timeout):
                    cleared = False
            if cleared:
                timeutils.print_log('当前文献组的文档记录及向量切片均已删除')
                return True
            if attempt < retries:
                time.sleep(interval)
        raise RuntimeError('当前文献组仍存在文档记录/向量切片')
    except Exception as exc:
        timeutils.print_log(f'联合删除失败: {exc}')
        return False


def delete_document_from_db(filename, doc_id=None):
    """Delete both metadata and vector chunks using the document owner's key."""
    try:
        if not doc_id:
            timeutils.print_log(f'删除失败，找不到文档ID: {filename}')
            return False
        dataset_id = str(getattr(configs, 'DIFY_DOC_KB_ID', '') or '').strip()
        if not dataset_id:
            timeutils.print_log('删除失败，DIFY_DOC_KB_ID为空')
            return False

        base_url = _get_public_api_base()
        headers = _get_public_api_headers()
        timeout = int(getattr(configs, 'RAGFLOW_REQUEST_TIMEOUT', 180))
        documents_url = f'{base_url}/datasets/{dataset_id}/documents'

        timeutils.print_log(
            f'通过RAGFlow官方API删除文档及向量切片: {filename}, ID: {doc_id}'
        )
        response = requests.delete(
            documents_url,
            headers=headers,
            json={'ids': [str(doc_id)]},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        code = _api_code(payload)
        if code not in (0, None):
            timeutils.print_log(
                'RAGFlow删除失败: '
                + str(payload.get('message') or payload.get('retmsg') or code)
            )
            return False

        retries = int(getattr(configs, 'DOCUMENT_DELETE_VERIFY_RETRIES', 15))
        interval = float(
            getattr(configs, 'DOCUMENT_DELETE_VERIFY_INTERVAL', 1)
        )
        for attempt in range(retries + 1):
            document_exists = _document_still_exists(
                documents_url, headers, doc_id, timeout
            )
            chunks_exist = _chunks_still_exist(
                base_url, dataset_id, headers, doc_id, timeout
            )
            if not document_exists and not chunks_exist:
                timeutils.print_log(f'文档记录和向量切片均已删除: {filename}')
                return True
            if attempt < retries:
                time.sleep(interval)

        timeutils.print_log(
            f'文档或向量切片仍存在，停止后续处理: {filename}'
        )
        return False
    except Exception as exc:
        timeutils.print_log(f'通过RAGFlow官方API删除失败: {exc}')
        return False
