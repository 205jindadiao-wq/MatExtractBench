"""Offline contract tests. No real RAGFlow calls or credentials are used."""
import csv
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
config = types.ModuleType('ragflows.configs')
config.DIFY_DOC_KB_ID = 'dataset'
config.CHAT_ID = 'chat'
config.KB_NAME = 'test'
config.OPENAI_API_KEY = 'key'
config.OPENAI_BASE_URL = 'http://example/api/v1/chats_openai'
config.NANOZYME_XLSX_PATH = 'names.xlsx'
config.PEROVSKITE_XLSX_PATH = ''
config.DELETE_FROM_DATABASE = True
config.ONLY_UPLOAD = False
config.EXTRACTION_WAIT_TIME = 0
config.EXTRACTION_MAX_RETRIES = 2
config.DOCUMENT_DELETE_VERIFY_RETRIES = 0
api = types.ModuleType('ragflows.api')
package = types.ModuleType('ragflows')
package.configs, package.api = config, api
sys.modules.update({'ragflows': package, 'ragflows.configs': config, 'ragflows.api': api})
utils = types.ModuleType('utils')
utils.timeutils = types.SimpleNamespace(
    print_log=lambda message: None,
    monitor=lambda function: function,
)
utils.fileutils = types.SimpleNamespace(
    get_cache_dir=lambda: '.',
    save=lambda *args, **kwargs: None,
)
sys.modules['utils'] = utils
requests = types.ModuleType('requests')
requests.get, requests.post, requests.delete = Mock(), Mock(), Mock()
sys.modules['requests'] = requests


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'ragflows' / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


db = load('ragflows.db_utils_fixed', 'db_utils_fixed.py')
load('ragflows.param_extractor', 'param_extractor.py')
p = load('ragflows.perovskite', 'perovskite.py')
real_api = load('ragflows.api_real', 'api.py')


def answer(pce=20):
    values = dict.fromkeys(p.PARAMETERS)
    values['PCE (%)'] = pce
    values['buried interface passivation agent'] = 'KBr, PMMA'
    return json.dumps({'found': True, 'parameters': values})


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        config.DOC_DIR = str(self.root / 'pdf')
        config.PEROVSKITE_OUTPUT_DIR = str(self.root / 'out')
        Path(config.DOC_DIR).mkdir()
        config.ONLY_UPLOAD = False
        config.DELETE_FROM_DATABASE = True

    def pair(self, number):
        for suffix in ('', '-SI'):
            (Path(config.DOC_DIR) / f'{number}{suffix}.pdf').touch()

    def test_pairing_and_order(self):
        self.pair(515)
        self.pair(516)
        pairs = p.discover_pairs(config.DOC_DIR)
        self.assertEqual([x[0] for x in pairs], ['516', '515'])
        self.assertEqual(pairs[0][1]['si'].name, '516-SI.pdf')

    def test_main_only_is_allowed(self):
        (Path(config.DOC_DIR) / '516.pdf').touch()
        pairs = p.discover_pairs(config.DOC_DIR)
        self.assertEqual(set(pairs[0][1]), {'main'})

    def test_si_only_is_allowed(self):
        (Path(config.DOC_DIR) / '516-SI.pdf').touch()
        pairs = p.discover_pairs(config.DOC_DIR)
        self.assertEqual(set(pairs[0][1]), {'si'})

    def test_duplicate_number_rejected(self):
        self.pair(516)
        (Path(config.DOC_DIR) / '0516.pdf').touch()
        with self.assertRaises(ValueError):
            p.discover_pairs(config.DOC_DIR)

    def test_schema_and_null(self):
        values = p.parse_answer(answer())
        self.assertEqual(values['PCE (%)'], 20)
        self.assertIsNone(values['FF (%)'])
        self.assertEqual(p.parse_answer('{"found":false}'), None)
        with self.assertRaises(ValueError):
            p.parse_answer('{"found":true,"parameters":{}}')
        self.assertEqual(p.parse_answer(answer('20%'))['PCE (%)'], 20.0)
        with self.assertRaises(ValueError):
            p.parse_answer(answer(True))

    def test_json_with_trailing_text_and_missing_found_is_accepted(self):
        self.assertEqual(p.parse_answer(answer() + '\nSource: paper'), p.parse_answer(answer()))
        direct = json.dumps(p.parse_answer(answer()))
        self.assertEqual(p.parse_answer(direct), p.parse_answer(answer()))

    def test_delimited_and_nested_partial_outputs_are_accepted(self):
        line = (
            'FOUND=1|||PCE=23.6|||VOC=1.169|||JSC=25.31|||FF=79.72|||'
            'BURIED=BTS, TMPU|||ADDITIVES=null|||INTERFACE=2-Br-PEAI'
        )
        values = p.parse_answer(line)
        self.assertEqual(values['PCE (%)'], 23.6)
        self.assertEqual(values['buried interface passivation agent'], 'BTS, TMPU')
        self.assertIsNone(values['perovskite layer additives'])
        nested = json.dumps({'title': '516.pdf', 'content': {
            'pristine_perovskite': {'voc': 1.12, 'jsc': 24.92, 'ff': 74.22, 'pce': 20.73}
        }})
        values = p.parse_answer(nested)
        self.assertEqual(values['PCE (%)'], 20.73)
        self.assertIsNone(values['perovskite interface passivation agent'])

    def test_partial_success_including_si_only_material(self):
        extractor = p.PerovskiteExtractor()
        extractor.load_evidence = Mock(return_value='MAIN: metrics. SI: Good material.')
        extractor.complete_pair = Mock(side_effect=['bad', 'bad', 'bad', answer()])
        docs = [{'id': 'a', 'name': '516.pdf'}, {'id': 'b', 'name': '516-SI.pdf'}]
        rows, skipped = extractor.extract('516', ['Bad', 'Good'], docs)
        self.assertEqual([row[1] for row in rows], ['Good'])
        self.assertEqual(skipped[0]['catalyst'], 'Bad')
        self.assertEqual(len(rows[0]), 9)
        self.assertEqual(extractor.complete_pair.call_args.args[1], ['a', 'b'])

    def test_retrieval_query_is_short_and_rules_are_not_user_query(self):
        extractor = p.PerovskiteExtractor()
        extractor.load_evidence = Mock(return_value='MAIN and SI evidence')
        extractor.complete_pair = Mock(return_value=answer())
        documents = [{'id': 'a', 'name': '516.pdf'}, {'id': 'b', 'name': '516-SI.pdf'}]
        extractor.extract('516', ['Target Material'], documents)
        messages = extractor.complete_pair.call_args.args[0]
        user_messages = [item['content'] for item in messages if item['role'] == 'user']
        self.assertEqual(len(user_messages), 1)
        self.assertLess(len(user_messages[0]), 400)
        self.assertIn('Target Material', user_messages[0])
        self.assertIn('PCE (%)', messages[0]['content'])
        self.assertEqual(messages[0]['role'], 'system')

    def test_all_null_retries_in_groups_and_preserves_responses(self):
        extractor = p.PerovskiteExtractor()
        extractor.load_evidence = Mock(return_value='main and SI')
        empty = json.dumps({'found': True, 'parameters': dict.fromkeys(p.PARAMETERS)})
        extractor.complete_pair = Mock(side_effect=[empty, 'PCE=21.43|||VOC=1.13',
                                                   'BURIED=KBr|||ADDITIVES=null|||INTERFACE=null'])
        rows, skipped = extractor.extract('516', ['Good'], [{'id': 'a'}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2:4], [21.43, 1.13])
        self.assertEqual(rows[0][6], 'KBr')
        self.assertEqual(skipped, [])
        self.assertEqual(len(extractor.last_attempts), 3)
        self.assertEqual(extractor.last_attempts[0]['response'], empty)

    def test_all_null_after_retry_is_skipped(self):
        extractor = p.PerovskiteExtractor()
        extractor.load_evidence = Mock(return_value='evidence')
        empty = 'FOUND=1|||PCE=null|||VOC=null|||JSC=null|||FF=null|||BURIED=null|||ADDITIVES=null|||INTERFACE=null'
        extractor.complete_pair = Mock(return_value=empty)
        rows, skipped = extractor.extract('516', ['Empty'], [{'id': 'a'}])
        self.assertEqual(rows, [])
        self.assertEqual(len(skipped[0]['attempts']), 3)
        with self.assertRaises(ValueError):
            p.parse_answer(empty)

    def test_standard_unit_keys_preserve_numbers_and_zero(self):
        values = dict.fromkeys(p.PARAMETERS)
        values.update({'PCE (%)': 0, 'VOC (V)': 1.13, 'JSC (mA cm-2)': 23.55, 'FF (%)': 80.53})
        self.assertEqual(p.parse_answer(json.dumps({'parameters': values})), values)

    def test_system_failure_propagates(self):
        extractor = p.PerovskiteExtractor()
        extractor.load_evidence = Mock(return_value='evidence')
        extractor.complete_pair = Mock(side_effect=RuntimeError('server failed'))
        with self.assertRaises(RuntimeError):
            extractor.extract('516', ['Good'], [{'id': 'a'}, {'id': 'b'}])

    def test_both_evidence_sources_and_no_truncation(self):
        extractor = p.PerovskiteExtractor()
        extractor._validate_chat_dataset_binding = Mock()
        extractor._fetch_document_chunks = Mock(side_effect=[[{'content': 'MAIN_TEXT'}], [{'content': 'SI_TEXT'}]])
        docs = [{'id': 'a', 'name': '516.pdf'}, {'id': 'b', 'name': '516-SI.pdf'}]
        evidence = extractor.load_evidence(docs)
        self.assertIn('MAIN_TEXT', evidence)
        self.assertIn('SI_TEXT', evidence)
        extractor._fetch_document_chunks = Mock(return_value=[{'content': 'x' * 120001}])
        with self.assertRaises(RuntimeError):
            extractor.load_evidence(docs)

    def test_request_sends_two_document_ids(self):
        extractor = p.PerovskiteExtractor()
        extractor.base_url = 'http://example/api/v1/chats_openai'
        extractor.chat_id = 'chat'
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': answer()}}]}
        with patch.object(requests, 'post', return_value=response) as post:
            extractor.complete_pair([{'role': 'user', 'content': 'question'}], ['a', 'b'])
        self.assertEqual(post.call_args.kwargs['json']['messages'][-1]['doc_ids'], ['a', 'b'])

    def test_csv_columns_and_commas(self):
        row = ['516', 'Good'] + list(p.parse_answer(answer()).values())
        p.save_results(self.root, '516', [], [row], [])
        csv_path = next(self.root.glob('*.csv'))
        with csv_path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], p.HEADER)
        self.assertEqual(len(rows[1]), 9)
        self.assertEqual(rows[1][6], 'KBr, PMMA')
        self.assertEqual(rows[1][3], 'null')
        master_path = self.root / 'perovskite_results.csv'
        self.assertTrue(master_path.is_file())

    def test_empty_result_still_writes_csv_header(self):
        p.save_results(self.root, '516', [], [], [{'reason': 'no data'}])
        csv_path = next(path for path in self.root.glob('516_*.csv'))
        with csv_path.open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows, [p.HEADER])

    def fake_api(self, events):
        documents = {}
        api.check_api_url = Mock(return_value=(True, 'ok'))
        api.get_document_by_name = Mock(side_effect=lambda name: documents.get(name))
        api.is_succeed = lambda result: result['code'] == 0
        def upload(path, *args):
            name = Path(path).name
            events.append(('upload', name))
            document = {'id': name, 'name': name, 'progress': 0}
            documents[name] = document
            return {'code': 0, 'data': [document]}
        api.upload_file_to_kb = Mock(side_effect=upload)
        api.get_document_by_id = Mock(side_effect=lambda doc_id: documents[doc_id])
        def parse(name, doc_id):
            events.append(('parse', name))
            documents[name]['progress'] = 1
            return True
        api.parse_chunks_with_check = Mock(side_effect=parse)
        return documents

    def test_pipeline_and_cleanup_resume(self):
        self.pair(516)
        events = []
        self.fake_api(events)
        def extract(paper_id, names, docs):
            events.append(('extract', paper_id))
            self.assertEqual(len(docs), 2)
            self.assertEqual([x[0] for x in events[:4]], ['upload', 'upload', 'parse', 'parse'])
            return [['516', 'Good'] + [None] * 7], []
        with patch.object(p.PerovskiteExtractor, 'extract', side_effect=extract) as extraction:
            with patch.object(p, 'delete_document_group', return_value=False):
                with self.assertRaises(RuntimeError):
                    p.run(lambda path: {'516': ['Good']})
            self.assertTrue(list(Path(config.PEROVSKITE_OUTPUT_DIR).glob('*.csv')))
            with patch.object(p, 'delete_document_group', return_value=True) as deletion:
                p.run(lambda path: {'516': ['Good']})
                deletion.assert_called_once()
            self.assertEqual(extraction.call_count, 1)
        state = json.loads(next(Path(config.PEROVSKITE_OUTPUT_DIR).glob('.perovskite*.json')).read_text())
        self.assertEqual(state['completed'], ['516'])
        self.assertIsNone(state['pending'])

    def test_parse_failure_prevents_extraction_and_deletion(self):
        self.pair(516)
        self.fake_api([])
        api.parse_chunks_with_check = Mock(return_value=False)
        with patch.object(p.PerovskiteExtractor, 'extract') as extract, patch.object(p, 'delete_document_group') as delete:
            with self.assertRaises(RuntimeError):
                p.run(lambda path: {'516': ['Good']})
            extract.assert_not_called()
            delete.assert_not_called()

    def test_save_failure_prevents_deletion(self):
        self.pair(516)
        self.fake_api([])
        with patch.object(p.PerovskiteExtractor, 'extract', return_value=([], [])), \
             patch.object(p, 'save_results', side_effect=OSError('disk full')), \
             patch.object(p, 'delete_document_group') as delete:
            with self.assertRaises(OSError):
                p.run(lambda path: {'516': ['Good']})
            delete.assert_not_called()

    def test_next_group_starts_only_after_cleanup(self):
        self.pair(516)
        self.pair(515)
        events = []
        self.fake_api(events)
        def delete(documents):
            events.append(('delete', documents[0]['name']))
            return True
        with patch.object(p.PerovskiteExtractor, 'extract', return_value=([], [{'reason': 'no data'}])), \
             patch.object(p, 'delete_document_group', side_effect=delete):
            p.run(lambda path: {'516': ['Bad'], '515': ['Bad']})
        self.assertLess(events.index(('delete', '516.pdf')), events.index(('upload', '515.pdf')))
        self.assertEqual(len(list(Path(config.PEROVSKITE_OUTPUT_DIR).glob('[0-9]*.csv'))), 2)
        self.assertEqual(len(list(Path(config.PEROVSKITE_OUTPUT_DIR).glob('[0-9]*.json'))), 2)

    def test_existing_documents_are_reused(self):
        self.pair(516)
        events = []
        documents = self.fake_api(events)
        for name in ('516.pdf', '516-SI.pdf'):
            documents[name] = {'name': name, 'id': name, 'progress': 1}
        pair = p.discover_pairs(config.DOC_DIR)[0][1]
        prepared = p.prepare_pair(pair)
        self.assertEqual(len(prepared), 2)
        api.upload_file_to_kb.assert_not_called()
        api.parse_chunks_with_check.assert_not_called()

    def test_single_document_is_uploaded_parsed_and_prepared(self):
        (Path(config.DOC_DIR) / '516.pdf').touch()
        events = []
        self.fake_api(events)
        group = p.discover_pairs(config.DOC_DIR)[0][1]
        prepared = p.prepare_pair(group)
        self.assertEqual([item['name'] for item in prepared], ['516.pdf'])
        self.assertEqual(events, [('upload', '516.pdf'), ('parse', '516.pdf')])

    def test_group_delete_one_request_and_verify_both(self):
        response = Mock()
        response.json.return_value = {'code': 0, 'data': {'docs': [{'id': 'a'}, {'id': 'b'}]}}
        deletion_response = Mock()
        deletion_response.json.return_value = {'code': 0}
        with patch.object(db, '_get_public_api_base', return_value='http://example/api/v1'), \
             patch.object(db, '_get_public_api_headers', return_value={}), \
             patch.object(requests, 'get', return_value=response), \
             patch.object(requests, 'delete', return_value=deletion_response) as delete, \
             patch.object(db, '_document_still_exists', return_value=False) as docs, \
             patch.object(db, '_chunks_still_exist', return_value=False) as chunks:
            self.assertTrue(db.delete_document_group([{'id': 'a'}, {'id': 'b'}]))
            self.assertEqual(delete.call_args.kwargs['json'], {'ids': ['a', 'b']})
            self.assertEqual(docs.call_count, 2)
            self.assertEqual(chunks.call_count, 2)

    def test_group_delete_accepts_one_document(self):
        response = Mock()
        response.json.return_value = {'code': 0, 'data': {'docs': [{'id': 'a'}]}}
        deletion_response = Mock()
        deletion_response.json.return_value = {'code': 0}
        with patch.object(db, '_get_public_api_base', return_value='http://example/api/v1'), \
             patch.object(db, '_get_public_api_headers', return_value={}), \
             patch.object(requests, 'get', return_value=response), \
             patch.object(requests, 'delete', return_value=deletion_response) as delete, \
             patch.object(db, '_document_still_exists', return_value=False), \
             patch.object(db, '_chunks_still_exist', return_value=False):
            self.assertTrue(db.delete_document_group([{'id': 'a'}]))
            self.assertEqual(delete.call_args.kwargs['json'], {'ids': ['a']})

    def test_foreign_same_name_document_is_treated_as_absent(self):
        response = Mock()
        response.json.return_value = {
            'code': 102,
            'message': "You don't own the document 515.pdf.",
        }
        with patch.object(requests, 'get', return_value=response):
            self.assertIsNone(real_api.get_document_by_name('515.pdf'))


if __name__ == '__main__':
    unittest.main()
