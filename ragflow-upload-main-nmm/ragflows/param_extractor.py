#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract nanozyme parameters from exactly one RAGFlow document."""

import csv
import io
import json
import os
import re
import time
import unicodedata
from datetime import datetime

import requests

from ragflows import configs
from utils import timeutils


EXPECTED_HEADER = [
    'Nanozyme Name', 'Classification', 'O', 'N', 'P', 'S', 'Si',
    'Se', 'B', 'F', 'Cl', 'Br', 'I', 'Metal oxidation state',
    'Shape', 'Size (nm)', 'Surface treatment', 'Dispersion medium',
    'Optimal pH', 'Optimal temperature (C)', 'Substrate', 'Km (mM)',
    'Vmax (uM s-1)', 'Kcat (s-1)',
]


class NanozymeExtractor:
    def __init__(self, chat_id=None):
        self.chat_id = chat_id or getattr(configs, 'CHAT_ID', '')
        self.api_key = str(getattr(configs, 'OPENAI_API_KEY', '') or '').strip()
        self.base_url = str(getattr(configs, 'OPENAI_BASE_URL', '') or '').rstrip('/')
        self.dataset_id = str(getattr(configs, 'DIFY_DOC_KB_ID', '') or '').strip()
        self.request_timeout = int(getattr(configs, 'RAGFLOW_REQUEST_TIMEOUT', 180))
        self.max_context_chars = int(
            getattr(configs, 'NANOZYME_MAX_CONTEXT_CHARS', 8000)
        )
        self.last_validated_names = []
        self.last_unmatched_names = []
        self.last_failed_names = []
        self.material_not_found = False
        self.model_extraction_failed = False

        configured_api_base = str(
            getattr(configs, 'RAGFLOW_PUBLIC_API_BASE_URL', '') or ''
        ).rstrip('/')
        if configured_api_base:
            self.ragflow_api_base = configured_api_base
        elif '/chats_openai' in self.base_url:
            self.ragflow_api_base = self.base_url.rsplit('/chats_openai', 1)[0]
        elif '/openai' in self.base_url:
            self.ragflow_api_base = self.base_url.rsplit('/openai', 1)[0]
        else:
            self.ragflow_api_base = self.base_url

    def _auth_headers(self):
        token = self.api_key
        if token and not token.lower().startswith('bearer '):
            token = f'Bearer {token}'
        return {'Authorization': token, 'Content-Type': 'application/json'}

    @staticmethod
    def _normalize_chemical_text(value):
        value = unicodedata.normalize('NFKC', str(value or '')).lower()
        return re.sub(r'[^a-z0-9]+', '', value)

    @staticmethod
    def _chemical_tokens(value):
        value = unicodedata.normalize('NFKC', str(value or '')).lower()
        return re.findall(r'[a-z0-9]+', value)

    @classmethod
    def _contains_chemical_name(cls, content, nanozyme_name):
        """Match full token sequences and tolerate Fe2O3/Fe₂O₃ typography."""
        target_tokens = cls._chemical_tokens(nanozyme_name)
        content_tokens = cls._chemical_tokens(content)
        if not target_tokens or len(target_tokens) > len(content_tokens):
            return False
        target = ''.join(target_tokens)
        width = len(target_tokens)
        return any(
            ''.join(content_tokens[index:index + width]) == target
            for index in range(len(content_tokens) - width + 1)
        )

    @staticmethod
    def _chunk_content(chunk):
        return str(
            chunk.get('content') or chunk.get('content_with_weight') or ''
        ).strip()

    @staticmethod
    def _api_code(payload):
        return payload.get('code', payload.get('retcode', 0))

    def _validate_chat_dataset_binding(self):
        """Fail clearly when upload KB and chat-assistant KB are different."""
        if not self.chat_id or not self.dataset_id:
            raise ValueError('CHAT_ID or DIFY_DOC_KB_ID is empty')

        response = requests.get(
            f'{self.ragflow_api_base}/chats',
            headers=self._auth_headers(),
            params={'id': self.chat_id, 'page': 1, 'page_size': 10},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if self._api_code(payload) not in (0, None):
            raise RuntimeError(
                payload.get('message') or payload.get('retmsg')
                or 'Unable to inspect RAGFlow chat configuration'
            )

        data = payload.get('data') or {}
        chats = data if isinstance(data, list) else data.get('chats') or []
        chat = next(
            (item for item in chats if str(item.get('id')) == str(self.chat_id)),
            None,
        )
        if not chat:
            raise RuntimeError(f'RAGFlow chat not found: {self.chat_id}')

        datasets = chat.get('datasets') or []
        dataset_ids = {str(item.get('id')) for item in datasets}
        if self.dataset_id not in dataset_ids:
            names = ', '.join(str(item.get('name')) for item in datasets) or 'none'
            raise RuntimeError(
                f'Configuration mismatch: chat {chat.get("name") or self.chat_id} '
                f'is bound to [{names}], but uploads use dataset {self.dataset_id}'
            )

    def _fetch_document_chunks(self, doc_id):
        if not self.dataset_id:
            raise ValueError('DIFY_DOC_KB_ID is empty; cannot load chunks')

        url = (
            f'{self.ragflow_api_base}/datasets/{self.dataset_id}'
            f'/documents/{doc_id}/chunks'
        )
        chunks = []
        page = 1
        page_size = 100
        while True:
            response = requests.get(
                url,
                headers=self._auth_headers(),
                params={'page': page, 'page_size': page_size},
                timeout=self.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
            code = self._api_code(payload)
            if code not in (0, None):
                raise RuntimeError(
                    payload.get('message') or payload.get('retmsg')
                    or f'RAGFlow chunk API failed with code {code}'
                )
            data = payload.get('data') or {}
            page_chunks = data.get('chunks') or []
            chunks.extend(page_chunks)
            total = int(data.get('total') or len(chunks))
            if not page_chunks or len(chunks) >= total:
                break
            page += 1

        timeutils.print_log(
            f'已从当前文档 {doc_id} 读取 {len(chunks)} 个切片'
        )
        return chunks

    def _find_relevant_chunk_indexes(self, chunks, nanozyme_name):
        if not self._chemical_tokens(nanozyme_name):
            return []
        direct_hits = [
            index for index, chunk in enumerate(chunks)
            if self._contains_chemical_name(
                self._chunk_content(chunk), nanozyme_name
            )
        ]
        selected = set()
        for index in direct_hits:
            selected.update(range(max(0, index - 1), min(len(chunks), index + 2)))
        return sorted(selected)

    def _build_document_evidence(self, chunks, matched_indexes):
        indexes = sorted({
            index for values in matched_indexes.values() for index in values
        })
        parts = []
        used = 0
        for index in indexes:
            content = self._chunk_content(chunks[index])
            if not content:
                continue
            part = f'[Document chunk {index + 1}]\n{content}'
            remaining = self.max_context_chars - used - (2 if parts else 0)
            if remaining <= 0:
                break
            part = part[:remaining]
            parts.append(part)
            used += len(part) + (2 if len(parts) > 1 else 0)
        return '\n\n'.join(parts)

    def _chat_completion(self, messages, doc_id):
        """Use RAGFlow OpenAI API while restricting retrieval to one doc_id."""
        scoped_messages = [dict(message) for message in messages]
        scoped_messages[-1]['doc_ids'] = [str(doc_id)]
        response = requests.post(
            f'{self.base_url}/{self.chat_id}/chat/completions',
            headers=self._auth_headers(),
            json={
                'model': getattr(configs, 'RAGFLOW_CHAT_MODEL', 'ragflow-model'),
                'messages': scoped_messages,
                'stream': False,
                'extra_body': {
                    'reference': getattr(configs, 'INCLUDE_REFERENCES', False),
                },
            },
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get('choices') or []
        if not choices:
            raise RuntimeError(
                payload.get('message') or payload.get('retmsg')
                or 'RAGFlow returned no choices'
            )
        return str(
            (choices[0].get('message') or {}).get('content') or ''
        ).strip()

    @staticmethod
    def _is_not_found_answer(content):
        value = str(content or '').lower()
        markers = (
            '知识库中未找到', '未找到您要的答案',
            'do not contain any information',
            'does not contain any information',
            'no data is available', 'not found in the provided',
        )
        return any(marker in value for marker in markers)

    @classmethod
    def _clean_and_validate_csv(cls, content, expected_names=None):
        cleaned = str(content or '').strip().lstrip('\ufeff')
        cleaned = re.sub(r'^```(?:csv)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
        rows = list(csv.reader(io.StringIO(cleaned)))
        if len(rows) < 2:
            raise ValueError('提取结果没有CSV数据行')
        if rows[0] != EXPECTED_HEADER:
            raise ValueError('提取结果未使用要求的24列CSV表头')
        for row_number, row in enumerate(rows[1:], start=2):
            if len(row) != len(EXPECTED_HEADER):
                raise ValueError(
                    f'CSV第{row_number}行有{len(row)}列，要求{len(EXPECTED_HEADER)}列'
                )
        if expected_names:
            actual = [row[0].strip() for row in rows[1:]]
            if len(actual) != len(expected_names):
                raise ValueError(
                    f'返回{len(actual)}行，预期每个名称一行，共{len(expected_names)}行'
                )
            actual_norm = sorted(cls._normalize_chemical_text(x) for x in actual)
            expected_norm = sorted(
                cls._normalize_chemical_text(x) for x in expected_names
            )
            if actual_norm != expected_norm:
                raise ValueError('CSV中的名称与当前文档已验证名称不一致')
        return cleaned

    @classmethod
    def _json_to_csv(cls, content, expected_names):
        """Parse model JSON and let Python generate correctly quoted CSV."""
        cleaned = str(content or '').strip().lstrip('\ufeff')
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            array_start, array_end = cleaned.find('['), cleaned.rfind(']')
            object_start, object_end = cleaned.find('{'), cleaned.rfind('}')
            if array_start >= 0 and array_end > array_start:
                data = json.loads(cleaned[array_start:array_end + 1])
            elif object_start >= 0 and object_end > object_start:
                data = json.loads(cleaned[object_start:object_end + 1])
            else:
                raise ValueError('模型未返回有效JSON')

        if isinstance(data, dict):
            data = data.get('results') or data.get('data') or [data]
        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            raise ValueError('模型JSON必须是对象数组')
        if len(data) != len(expected_names):
            raise ValueError(
                f'模型返回{len(data)}条记录，要求{len(expected_names)}条'
            )

        output = io.StringIO()
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(EXPECTED_HEADER)
        actual_names = []
        for item in data:
            normalized_keys = {
                cls._normalize_chemical_text(key): value
                for key, value in item.items()
            }
            row = []
            for column in EXPECTED_HEADER:
                value = item.get(column)
                if value is None:
                    value = normalized_keys.get(
                        cls._normalize_chemical_text(column), 'Unknown'
                    )
                if isinstance(value, list):
                    value = '/'.join(str(part) for part in value)
                if value is None or str(value).strip() == '':
                    value = 'Unknown'
                row.append(str(value).replace('\r', ' ').replace('\n', ' ').strip())
            actual_names.append(row[0])
            writer.writerow(row)

        actual_norm = sorted(cls._normalize_chemical_text(x) for x in actual_names)
        expected_norm = sorted(
            cls._normalize_chemical_text(x) for x in expected_names
        )
        if actual_norm != expected_norm:
            raise ValueError('JSON中的nanozyme名称与当前PDF已验证名称不一致')
        return cls._clean_and_validate_csv(output.getvalue(), expected_names)

    @classmethod
    def _clean_and_validate_model_output(cls, content, expected_names):
        """Prefer JSON, while accepting already-valid CSV for compatibility."""
        try:
            return cls._json_to_csv(content, expected_names)
        except Exception as json_error:
            try:
                return cls._clean_and_validate_csv(content, expected_names)
            except Exception as csv_error:
                raise ValueError(
                    f'输出格式无效（JSON: {json_error}; CSV: {csv_error}）'
                ) from csv_error

    @classmethod
    def _parse_delimited_row(cls, content, expected_name):
        """Parse one model row using a delimiter that cannot conflict with commas."""
        cleaned = str(content or '').strip().lstrip('\ufeff')
        cleaned = re.sub(r'^```(?:text|txt|csv)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
        candidates = [
            line.strip() for line in cleaned.splitlines()
            if line.count('|||') >= len(EXPECTED_HEADER) - 1
        ]
        if not candidates:
            raise ValueError('模型未返回|||分隔的数据行')

        expected_normalized = cls._normalize_chemical_text(expected_name)
        selected = next(
            (
                line for line in candidates
                if expected_normalized in cls._normalize_chemical_text(
                    line.split('|||', 1)[0]
                )
            ),
            candidates[-1],
        )
        row = [value.strip() or 'Unknown' for value in selected.split('|||')]
        if len(row) != len(EXPECTED_HEADER):
            raise ValueError(
                f'分隔数据有{len(row)}个值，要求{len(EXPECTED_HEADER)}个'
            )
        if expected_normalized not in cls._normalize_chemical_text(row[0]):
            raise ValueError(f'返回的数据不是当前名称: {expected_name}')
        row[0] = expected_name
        return row

    @classmethod
    def _canonical_column(cls, label):
        key = cls._normalize_chemical_text(
            str(label or '').replace('**', '').replace('`', '')
        )
        exact = {
            cls._normalize_chemical_text(column): column
            for column in EXPECTED_HEADER
        }
        if key in exact:
            return exact[key]
        aliases = {
            'nanozyme': 'Nanozyme Name',
            'name': 'Nanozyme Name',
            'enzymeclass': 'Classification',
            'type': 'Classification',
            'metaloxidationstate': 'Metal oxidation state',
            'oxidationstate': 'Metal oxidation state',
            'morphology': 'Shape',
            'particlesize': 'Size (nm)',
            'surfacetreatmentfunctionalization': 'Surface treatment',
            'surfacefunctionalization': 'Surface treatment',
            'medium': 'Dispersion medium',
            'ph': 'Optimal pH',
            'temperature': 'Optimal temperature (C)',
        }
        if key in aliases:
            return aliases[key]
        prefix_aliases = (
            ('size', 'Size (nm)'),
            ('surfacetreatment', 'Surface treatment'),
            ('dispersionmedium', 'Dispersion medium'),
            ('optimalph', 'Optimal pH'),
            ('optimaltemperature', 'Optimal temperature (C)'),
            ('substrate', 'Substrate'),
            ('km', 'Km (mM)'),
            ('vmax', 'Vmax (uM s-1)'),
            ('kcat', 'Kcat (s-1)'),
        )
        return next(
            (column for prefix, column in prefix_aliases if key.startswith(prefix)),
            None,
        )

    @classmethod
    def _row_from_mapping(cls, values, expected_name):
        if not values:
            raise ValueError('结果中没有可识别的参数字段')
        row = []
        for column in EXPECTED_HEADER:
            value = values.get(column, 'Unknown')
            if value is None or str(value).strip() == '':
                value = 'Unknown'
            row.append(str(value).replace('\r', ' ').replace('\n', ' ').strip())
        returned_name = row[0]
        if returned_name != 'Unknown' and (
            cls._normalize_chemical_text(expected_name)
            not in cls._normalize_chemical_text(returned_name)
        ):
            raise ValueError(f'返回的数据不是当前名称: {expected_name}')
        row[0] = expected_name
        return row

    @classmethod
    def _parse_markdown_or_key_values(cls, content, expected_name):
        """Accept horizontal/vertical Markdown tables and label:value lists."""
        lines = [line.strip() for line in str(content or '').splitlines() if line.strip()]
        table_rows = []
        for line in lines:
            if '|' not in line:
                continue
            cells = [cell.strip().replace('**', '') for cell in line.strip('|').split('|')]
            if cells and not all(re.fullmatch(r':?-{2,}:?', cell) for cell in cells):
                table_rows.append(cells)

        # Horizontal table: one header row followed by one data row. Missing
        # columns are safe because unreported values are explicitly Unknown.
        for index, header_cells in enumerate(table_rows[:-1]):
            columns = [cls._canonical_column(cell) for cell in header_cells]
            if sum(column is not None for column in columns) < 2:
                continue
            data_cells = table_rows[index + 1]
            if len(data_cells) != len(header_cells):
                continue
            values = {
                column: value
                for column, value in zip(columns, data_cells)
                if column is not None
            }
            if values:
                return cls._row_from_mapping(values, expected_name)

        # Vertical Markdown table: | Parameter | Value |.
        vertical_values = {}
        for cells in table_rows:
            if len(cells) < 2:
                continue
            column = cls._canonical_column(cells[0])
            if column:
                vertical_values[column] = cells[1]
        if len(vertical_values) >= 2:
            return cls._row_from_mapping(vertical_values, expected_name)

        # Plain text list: Classification: POD, Size (nm): 20, ...
        key_values = {}
        for line in lines:
            match = re.match(r'^[-*\d.\s]*([^:=]{1,80})\s*[:=]\s*(.+)$', line)
            if not match:
                continue
            column = cls._canonical_column(match.group(1))
            if column:
                key_values[column] = match.group(2).strip().replace('**', '')
        if len(key_values) >= 2:
            return cls._row_from_mapping(key_values, expected_name)
        raise ValueError('未识别到Markdown表格或字段值列表')

    @classmethod
    def _parse_single_model_row(cls, content, expected_name):
        errors = []
        parsers = (
            lambda: cls._parse_delimited_row(content, expected_name),
            lambda: list(csv.reader(io.StringIO(
                cls._json_to_csv(content, [expected_name])
            )))[1],
            lambda: list(csv.reader(io.StringIO(
                cls._clean_and_validate_csv(content, [expected_name])
            )))[1],
            lambda: cls._parse_markdown_or_key_values(content, expected_name),
        )
        for parser in parsers:
            try:
                row = parser()
                if len(row) == len(EXPECTED_HEADER):
                    return row
            except Exception as exc:
                errors.append(str(exc))
        preview = re.sub(r'\s+', ' ', str(content or ''))[:300]
        raise ValueError(
            f'无法识别模型输出；预览: {preview}; 解析错误: {" | ".join(errors)}'
        )

    @classmethod
    def _parse_group_values(cls, content, expected_name, group_columns):
        """Map labeled values to columns; never infer missing positions."""
        cleaned = str(content or '').strip().lstrip('\ufeff')
        cleaned = re.sub(r'^```(?:text|txt|csv)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
        expected_count = len(group_columns)

        # Preferred form: Field=value|||Field=value. Because every value carries
        # its own label, omitted fields cannot shift neighboring columns.
        labeled_values = {}
        segments = []
        for line in cleaned.splitlines():
            segments.extend(line.split('|||'))
        for segment in segments:
            match = re.match(
                r'^\s*[-*\d.]*\s*([^:=]{1,100}?)\s*[:=]\s*(.*?)\s*$',
                segment,
            )
            if not match:
                continue
            column = cls._canonical_column(match.group(1))
            if column in group_columns:
                value = match.group(2).strip() or 'Unknown'
                labeled_values[column] = value
        if labeled_values:
            missing = [column for column in group_columns if column not in labeled_values]
            if missing:
                timeutils.print_log(
                    f'{expected_name}: 未返回字段按字段名补Unknown: {", ".join(missing)}'
                )
            return [labeled_values.get(column, 'Unknown') for column in group_columns]

        # Backward compatibility: accept positional output only when the count
        # is exact. Never pad a short positional row because that can shift data.
        for line in cleaned.splitlines():
            if '|||' not in line:
                continue
            values = [value.strip() or 'Unknown' for value in line.split('|||')]
            if values and (
                cls._normalize_chemical_text(expected_name)
                in cls._normalize_chemical_text(values[0])
            ):
                values = values[1:]
            if len(values) == expected_count:
                return values

        # If the assistant insists on JSON/Markdown, reuse the tolerant full-row
        # parser and take only this group's columns.
        try:
            full_row = cls._parse_single_model_row(content, expected_name)
            positions = [EXPECTED_HEADER.index(column) for column in group_columns]
            return [full_row[position] for position in positions]
        except Exception as exc:
            preview = re.sub(r'\s+', ' ', cleaned)[:300]
            raise ValueError(
                f'{expected_count}字段响应不完整；预览: {preview}; {exc}'
            ) from exc

    def extract_nanozyme_parameters_from_list(
        self, filename, doc_id, nanozyme_names, doc_index=None
    ):
        self.last_validated_names = []
        self.last_unmatched_names = []
        self.last_failed_names = []
        self.material_not_found = False
        self.model_extraction_failed = False
        try:
            if isinstance(nanozyme_names, list):
                candidates = [str(name).strip() for name in nanozyme_names]
            elif isinstance(nanozyme_names, str):
                candidates = [name.strip() for name in nanozyme_names.split(',')]
            else:
                timeutils.print_log('nanozyme_names参数格式错误')
                return None

            candidates = list(dict.fromkeys(name for name in candidates if name))
            if not candidates or not doc_id:
                timeutils.print_log('缺少有效nanozyme名称或文档ID')
                return None

            timeutils.print_log(f'开始提取: {filename}, 文档ID: {doc_id}')
            self._validate_chat_dataset_binding()
            chunks = self._fetch_document_chunks(doc_id)
            if not chunks:
                timeutils.print_log(f'当前文档没有已解析切片: {doc_id}')
                return None

            matched = {}
            unmatched = []
            for name in candidates:
                indexes = self._find_relevant_chunk_indexes(chunks, name)
                if indexes:
                    matched[name] = indexes
                else:
                    unmatched.append(name)

            if unmatched:
                self.last_unmatched_names = list(unmatched)
                timeutils.print_log(
                    f'XLSX与PDF映射不一致，当前文档未出现: {", ".join(unmatched)}'
                )

            names_to_extract = list(matched)
            if not names_to_extract:
                self.material_not_found = True
                timeutils.print_log('所有XLSX名称都未在当前PDF切片中找到，停止提取')
                return None

            max_retries = int(getattr(configs, 'EXTRACTION_MAX_RETRIES', 2))
            output = io.StringIO()
            writer = csv.writer(output, lineterminator='\n')
            writer.writerow(EXPECTED_HEADER)
            successful_names = []

            for name_index, name in enumerate(names_to_extract, 1):
                evidence = self._build_document_evidence(
                    chunks, {name: matched[name]}
                )
                groups = (
                    ('composition', EXPECTED_HEADER[1:14]),
                    ('physical', EXPECTED_HEADER[14:18]),
                    ('kinetic', EXPECTED_HEADER[18:24]),
                )
                row = [name]
                material_complete = True
                for group_index, (group_name, group_columns) in enumerate(groups, 1):
                    field_template = '|||'.join(
                        f'{column}=<value>' for column in group_columns
                    )
                    messages = [
                        {
                            'role': 'user',
                            'content': f'Find evidence about {name} in the selected document.',
                        },
                        {
                            'role': 'assistant',
                            'content': (
                                f'SOURCE EXCERPTS FROM DOCUMENT {doc_id}:\n{evidence}\n\n'
                                'Use these excerpts as the only source of parameter values.'
                            ),
                        },
                        {
                            'role': 'user',
                            'content': (
                                f'For {name}, return labeled field=value assignments on '
                                'one line separated by |||. Every value must keep its exact '
                                'field label. Do not include a header, JSON, Markdown, or '
                                'explanation. Keep each value under 12 words. For non-element '
                                'fields only, use Unknown when that field is unreported. '
                                'Classification must use CAT/HYL/OXD/POD/SOD. For the O, N, P, '
                                'S, Si, Se, B, F, Cl, Br, and I fields, judge whether the target '
                                f'nanozyme {name} itself contains each element: output 1 if it '
                                'contains the element and 0 if it does not; never output Unknown '
                                'for these element fields. Do not count elements that appear only '
                                'in substrates, buffers, solvents, or other assay reagents. '
                                'Use this exact template:\n'
                                f'{field_template}'
                            ),
                        },
                    ]

                    group_values = None
                    model_output_error_count = 0
                    system_error_count = 0
                    material_missing = False
                    for attempt in range(max_retries):
                        try:
                            content = self._chat_completion(messages, doc_id)
                            if self._is_not_found_answer(content):
                                material_missing = True
                                if name not in self.last_unmatched_names:
                                    self.last_unmatched_names.append(name)
                                timeutils.print_log(
                                    f'RAGFlow明确返回当前文档中未找到材料内容: {name}'
                                )
                                break
                            group_values = self._parse_group_values(
                                content, name, group_columns
                            )
                            break
                        except Exception as exc:
                            if isinstance(exc, ValueError):
                                model_output_error_count += 1
                            else:
                                system_error_count += 1
                            timeutils.print_log(
                                f'[{name_index}/{len(names_to_extract)}] {name} '
                                f'分组{group_index}/3第{attempt + 1}/{max_retries}次失败: {exc}'
                            )
                            if attempt + 1 < max_retries:
                                time.sleep(3 * (attempt + 1))
                    if material_missing:
                        material_complete = False
                        timeutils.print_log(
                            f'跳过材料 {name}：当前文档中没有可提取内容'
                        )
                        break
                    if group_values is None:
                        if model_output_error_count and not system_error_count:
                            self.model_extraction_failed = True
                            if name not in self.last_failed_names:
                                self.last_failed_names.append(name)
                            material_complete = False
                            timeutils.print_log(
                                f'跳过材料 {name}：{group_name}参数无法完整提取'
                            )
                            break
                        timeutils.print_log(
                            f'停止：{name}的{group_name}参数无法完整提取'
                        )
                        return None
                    row.extend(group_values)

                if not material_complete:
                    continue

                if len(row) != len(EXPECTED_HEADER):
                    self.model_extraction_failed = True
                    if name not in self.last_failed_names:
                        self.last_failed_names.append(name)
                    timeutils.print_log(f'跳过材料 {name}：合并后不是24个字段')
                    continue
                writer.writerow(row)
                successful_names.append(name)
                timeutils.print_log(
                    f'[{name_index}/{len(names_to_extract)}] {name} 提取成功'
                )

            self.last_validated_names = successful_names
            if not successful_names:
                if self.last_unmatched_names and not self.model_extraction_failed:
                    self.material_not_found = True
                timeutils.print_log('当前文档没有成功提取出任何完整材料记录')
                return None

            try:
                return self._clean_and_validate_csv(
                    output.getvalue(), successful_names
                )
            except ValueError as exc:
                self.model_extraction_failed = True
                timeutils.print_log(f'模型结果最终校验失败: {exc}')
                return None
        except Exception as exc:
            timeutils.print_log(f'提取流程失败: {exc}')
            return None

    def save_extraction_results(
        self, content, filename, doc_id, nanozyme_names
    ):
        try:
            names = (
                nanozyme_names if isinstance(nanozyme_names, list)
                else [x.strip() for x in str(nanozyme_names).split(',') if x.strip()]
            )
            output_dir = getattr(
                configs,
                'NANOZYME_OUTPUT_DIR',
                '/public/ly/hj/ragflow-data-qwenmax11------nmm',
            )
            os.makedirs(output_dir, exist_ok=True)
            base_name = os.path.splitext(filename)[0]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = os.path.join(
                output_dir,
                f'{base_name}_doc{doc_id}_nanozyme_{timestamp}.txt',
            )
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('=' * 70 + '\n')
                handle.write('NANOZYME PARAMETER EXTRACTION RESULTS\n')
                handle.write('=' * 70 + '\n')
                handle.write(f'Extraction Time: {datetime.now():%Y-%m-%d %H:%M:%S}\n')
                handle.write(f'Source Document: {filename}\n')
                handle.write(f'Document ID: {doc_id}\n')
                handle.write(f'Number of Nanozymes: {len(names)}\n')
                handle.write('=' * 70 + '\n\nNANOZYME NAME LIST:\n')
                for index, name in enumerate(names, 1):
                    handle.write(f'  {index}. {name}\n')
                handle.write('\n' + '=' * 70 + '\n\n')
                handle.write(content)
            timeutils.print_log(f'结果已保存: {path}')
            return path
        except Exception as exc:
            timeutils.print_log(f'保存结果失败: {exc}')
            return None


def extract_and_save_nanozyme(filename, doc_id, nanozyme_names, chat_id=None):
    extractor = NanozymeExtractor(chat_id)
    content = extractor.extract_nanozyme_parameters_from_list(
        filename, doc_id, nanozyme_names
    )
    if not content:
        return None
    return extractor.save_extraction_results(
        content,
        filename,
        doc_id,
        extractor.last_validated_names or nanozyme_names,
    )
