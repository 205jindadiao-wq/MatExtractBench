#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.path.append('.')
from ragflows import ragflowdb

db = ragflowdb.get_db()
if not db or not db.conn:
    print("? failed")
    sys.exit(1)

cursor = db.conn.cursor()

# Show all tables
cursor.execute("SHOW TABLES")
tables = cursor.fetchall()
print("all tables:")
for table in tables:
    print(f"  - {table[0]}")

print("\nCheck the structure of the document-related tables:")

# Check the structure of the document table
try:
    cursor.execute("DESCRIBE document")
    columns = cursor.fetchall()
    print("\n?? Structure of the document table:")
    for col in columns:
        print(f"  {col[0]} ({col[1]}) - {col[2]}")
except Exception as e:
    print(f"? Failed to query the document table: {e}")

# Check possible chunk table names
possible_chunk_tables = ['chunk', 'chunks', 'document_chunk', 'doc_chunk']
for table_name in possible_chunk_tables:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"\n? Found table '{table_name}', with {count} records")
        
        # Check table structure
        cursor.execute(f"DESCRIBE {table_name}")
        columns = cursor.fetchall()
        print(f"  Structure of the {table_name} table:")
        for col in columns:
            print(f"    {col[0]} ({col[1]}) - {col[2]}")
    except:
        pass

cursor.close()
db.conn.close()
