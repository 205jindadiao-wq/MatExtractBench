#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ragflows import ragflowdb
from utils import timeutils


def delete_document_from_db(filename, doc_id=None):

    try:
        # If doc_id is not provided, query from the database
        if not doc_id:
            doc_item = ragflowdb.get_doc_item_by_name(filename)
            if doc_item:
                doc_id = doc_item.get('id')
        
        if not doc_id:
            timeutils.print_log(f"failed: {filename}")
            return False
        
        db = ragflowdb.get_db()
        if not db or not db.conn:
            timeutils.print_log(f"failed")
            return False
        
        cursor = db.conn.cursor()
        
        timeutils.print_log(f"failed: {filename}")
        timeutils.print_log(f"   ID: {doc_id}")
        
        deleted_counts = {}
        
        try:
            # 1. First, delete the associated record from the file2document table
            try:
                cursor.execute("DELETE FROM file2document WHERE document_id = %s", (doc_id,))
                deleted_counts['file2document'] = cursor.rowcount
                timeutils.print_log(f"   Deleted file2document association: {deleted_counts['file2document']} records")
            except Exception as e:
                timeutils.print_log(f"?? Failed to delete file2document: {e}")
                deleted_counts['file2document'] = 0
            
            # 2. Try to delete the related file record from the file table
            # First, find the associated file_id
            try:
                cursor.execute("SELECT file_id FROM file2document WHERE document_id = %s", (doc_id,))
                file_ids = [row[0] for row in cursor.fetchall()]
                
                if file_ids:
                    # Delete file records
                    format_strings = ','.join(['%s'] * len(file_ids))
                    cursor.execute(f"DELETE FROM file WHERE id IN ({format_strings})", tuple(file_ids))
                    deleted_counts['file'] = cursor.rowcount
                    timeutils.print_log(f"   Deleted file records: {deleted_counts['file']} records")
                else:
                    deleted_counts['file'] = 0
            except Exception as e:
                timeutils.print_log(f"Failed to delete file records: {e}")
                deleted_counts['file'] = 0
            
            # 3. Delete the main record from the document table
            cursor.execute("DELETE FROM document WHERE id = %s", (doc_id,))
            deleted_counts['document'] = cursor.rowcount
            timeutils.print_log(f"   Deleted document records: {deleted_counts['document']} records")
            
            # Commit the transaction
            db.conn.commit()
            
            success = deleted_counts['document'] > 0
            
            if success:
                timeutils.print_log(f"Document deletion successful")
                timeutils.print_log(f"   Total deleted: {sum(deleted_counts.values())} records")
            else:
                timeutils.print_log(f"Document not found for deletion")
            
            return success
            
        except Exception as e:
            db.conn.rollback()
            timeutils.print_log(f"Deletion failed: {e}")
            return False
        
        finally:
            cursor.close()
        
    except Exception as e:
        timeutils.print_log(f"Failed to delete document from database: {e}")
        return False


def check_document_exists(filename):
    """
    Check if the document exists in the database
    
    Args:
        filename: document name
        
    Returns:
        tuple: (exists, document info)
    """
    try:
        db = ragflowdb.get_db()
        if not db or not db.conn:
            return False, None
        
        cursor = db.conn.cursor()
        cursor.execute("SELECT id, name, progress, kb_id FROM document WHERE name = %s", (filename,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            doc_info = {
                'id': result[0],
                'name': result[1],
                'progress': result[2],
                'kb_id': result[3]
            }
            return True, doc_info
        else:
            return False, None
            
    except Exception as e:
        timeutils.print_log(f"Failed to check if document exists: {e}")
        return False, None


def get_document_progress(doc_id):

    try:
        db = ragflowdb.get_db()
        if not db or not db.conn:
            return 0
        
        cursor = db.conn.cursor()
        cursor.execute("SELECT progress FROM document WHERE id = %s", (doc_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return result[0]
        else:
            return 0
            
    except Exception as e:
        timeutils.print_log(f"Failed to get document progress: {e}")
        return 0


def list_all_documents():
    """
    List all documents in the database
    
    Returns:
        list: List of documents
    """
    try:
        db = ragflowdb.get_db()
        if not db or not db.conn:
            return []
        
        cursor = db.conn.cursor()
        cursor.execute(""" 
            SELECT id, name, progress, kb_id, created_by, 
                   CASE WHEN progress = 1 THEN '? Parsed' ELSE '?? Parsing' END as status
            FROM document 
            ORDER BY name
        """)
        documents = cursor.fetchall()
        cursor.close()
        
        result = []
        for row in documents:
            doc = {
                'id': row[0],
                'name': row[1],
                'progress': row[2],
                'kb_id': row[3],
                'created_by': row[4],
                'status': row[5]
            }
            result.append(doc)
        
        return result
        
    except Exception as e:
        timeutils.print_log(f"Failed to list documents: {e}")
        return []


def get_knowledge_base_name(kb_id):

    try:
        db = ragflowdb.get_db()
        if not db or not db.conn:
            return "Unknown"
        
        cursor = db.conn.cursor()
        cursor.execute("SELECT name FROM knowledgebase WHERE id = %s", (kb_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            return result[0]
        else:
            return "Unknown"
            
    except Exception as e:
        timeutils.print_log(f"? Failed to get knowledge base name: {e}")
        return "Unknown"
