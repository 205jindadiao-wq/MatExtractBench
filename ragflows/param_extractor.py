#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from openai import OpenAI
import os
import csv
import pandas as pd
import time
from datetime import datetime
from ragflows import configs
from utils import timeutils


class NanozymeExtractor:
    def __init__(self, chat_id=None):
        self.chat_id = chat_id or getattr(configs, 'CHAT_ID', '9faec032ebb811f0b4ce0242ac150006')
        self.api_key = getattr(configs, 'OPENAI_API_KEY', 'ragflow-U4MThkYjI4ZDgzNDExZjA5NjJlMDI0Mm')
        self.base_url = getattr(configs, 'OPENAI_BASE_URL', 'http://192.168.66.36:80/api/v1/chats_openai')
        
        # Initialize OpenAI client
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=f"{self.base_url}/{self.chat_id}"
        )
    
    def extract_nanozyme_parameters_from_list(self, filename, doc_id, nanozyme_names, doc_index=None):
        """
        Extract nanozyme parameters from a single document - main function called by main.py
        
        Parameters:
        filename: Document filename
        doc_id: RAGFlow document ID
        nanozyme_names: Nanozyme name list or string
        doc_index: Document index in CSV (optional)
        
        Returns:
        str: Extraction results
        """
        try:
            # Debug information
            timeutils.print_log(f"=== Starting parameter extraction ===")
            timeutils.print_log(f"Document ID: {doc_id}")
            timeutils.print_log(f"Filename: {filename}")
            timeutils.print_log(f"Input nanozyme_names type: {type(nanozyme_names)}")
            
            # Process nanozyme_names parameter
            processed_nanozyme_names = []
            
            if isinstance(nanozyme_names, list):
                # If it's a list, use directly
                processed_nanozyme_names = nanozyme_names
                timeutils.print_log(f"nanozyme_names is list, contains {len(processed_nanozyme_names)} elements")
            elif isinstance(nanozyme_names, str):
                # If it's string, split by comma
                timeutils.print_log(f"nanozyme_names is string: '{nanozyme_names}'")
                names_list = [name.strip() for name in nanozyme_names.split(',') if name.strip()]
                processed_nanozyme_names = names_list
                timeutils.print_log(f"Parsed {len(processed_nanozyme_names)} names")
            else:
                timeutils.print_log(f"Unknown nanozyme_names type: {type(nanozyme_names)}")
                return "Error: nanozyme_names parameter format incorrect"
            
            # Remove duplicates
            unique_names = []
            seen = set()
            for name in processed_nanozyme_names:
                if name not in seen:
                    seen.add(name)
                    unique_names.append(name)
            
            processed_nanozyme_names = unique_names
            timeutils.print_log(f"After deduplication: {len(processed_nanozyme_names)} unique names")
            
            # Print name list
            for i, name in enumerate(processed_nanozyme_names):
                timeutils.print_log(f"  [{i+1}] {name}")
            
            if not processed_nanozyme_names:
                timeutils.print_log("Warning: No valid nanozyme names")
                return "No nanozyme names provided"
            
            # Build nanozyme list string
            nanozyme_list = "\n".join([f"{i+1}. {name}" for i, name in enumerate(processed_nanozyme_names)])
            
            # Build prompt
            prompt = f"""
            Extract parameters for the following nanozymes from document {doc_id}:
            
            Nanozyme list:
            {nanozyme_list}
            
            1. "PCE(%)": power conversion efficiency (%, numerical value)
            2. "VOC(V)": open-circuit voltage (V, numerical value)
            3. "JSC(mA cm-2)": short-circuit current density (mA/cm2, numerical value)
            4. "FF(%)": fill factor (%, numerical value)
            5. "buried interface passivation agent": chemical formula(s) of passivation agents applied before perovskite layer (on transport layer or SnO2
               solution). Multiple: comma-separated.
            6. "perovskite layer additives" : chemical formula(s) of additives dissolved in perovskite precursor solution. Multiple: comma-separated.
            7. "perovskite interface passivation agent": chemical formula(s) of passivation agents applied after perovskite annealing. Multiple: comma-separated.
            
            Rules:
            - If a parameter is not found, use null.
            - For passivation agents, output only chemical formulas (e.g., "PEAI", "KBr, PMMA").
            - For electrical parameters, output numerical values (e.g., 19.5).
            
            Present all information in a structured tabular format, ensuring each parameter corresponds precisely to each catalyst.
            The parameters should be presented in the following order:
            Output order: catalyst Name | PCE (%) | VOC (V) | JSC (mA cm-2) | FF (%) | buried interface passivation agent | perovskite layer additives |
                          perovskite interface passivation agent
            """
            
            # Build messages
            messages = [
                {"role": "system", "content": "You are a professional scientific data extraction assistant. Extract information exactly as requested."},
                {"role": "user", "content": prompt},
            ]

            timeutils.print_log(f"Starting parameter extraction from document {doc_id}...")
            
            # Add retry mechanism
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    timeutils.print_log(f"Attempt {attempt + 1} of {max_retries}...")
                    
                    # Use non-streaming response (more stable)
                    completion = self.client.chat.completions.create(
                        model="ragflow-model",
                        messages=messages,
                        stream=False,  # Changed to non-streaming
                        extra_body={"reference": getattr(configs, 'INCLUDE_REFERENCES', False)}
                    )

                    response = completion.choices[0].message
                    content = response.content
                    
                    timeutils.print_log(f"Extraction completed, response length: {len(content)} characters")
                    
                    # Check result
                    if content:
                        # Simple check if contains table
                        if '|' in content and ('Nanozyme' in content or 'nanozyme' in content):
                            timeutils.print_log("Extraction result contains table format")
                            # Show first few lines
                            lines = content.split('\n')
                            for i, line in enumerate(lines[:10]):
                                timeutils.print_log(f"  Line {i+1}: {line}")
                        else:
                            timeutils.print_log(f"Extraction result may not contain table")
                            timeutils.print_log(f"First 200 characters: {content[:200]}")
                    
                    return content
                    
                except Exception as e:
                    timeutils.print_log(f"Attempt {attempt + 1} failed: {str(e)[:100]}")
                    if attempt < max_retries - 1:
                        wait_time = 5 * (attempt + 1)  # Exponential backoff
                        timeutils.print_log(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                    else:
                        timeutils.print_log(f"All {max_retries} attempts failed")
                        return f"Extraction failed: {str(e)[:100]}"
            
            return None

        except Exception as e:
            timeutils.print_log(f"Extraction process error: {e}")
            return f"Extraction process error: {str(e)[:100]}"
    
    def save_extraction_results(self, content, filename, doc_id, nanozyme_names):
        """
        Save extraction results to file
        
        Parameters:
        content: Extracted content
        filename: Original filename
        doc_id: Document ID
        nanozyme_names: Nanozyme names
        
        Returns:
        str: Saved file path
        """
        try:
            # Process nanozyme_names parameter
            if isinstance(nanozyme_names, list):
                num_nanozymes = len(nanozyme_names)
                names_list = nanozyme_names
            else:
                # If string, split by comma
                names_str = str(nanozyme_names)
                names_list = [name.strip() for name in names_str.split(',') if name.strip()]
                num_nanozymes = len(names_list)
            
            # Define output directory
            output_dir = getattr(configs, 'NANOZYME_OUTPUT_DIR', "/public/ly/hj/ragflow-data-deepseek-r1:32b-xiaorong333")
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename
            base_name = os.path.splitext(filename)[0]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            txt_filename = f"{base_name}_doc{doc_id}_nanozyme_{timestamp}.txt"
            txt_path = os.path.join(output_dir, txt_filename)
            
            # Save to text file
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("NANOZYME PARAMETER EXTRACTION RESULTS\n")
                f.write("=" * 70 + "\n")
                f.write(f"Extraction Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source Document: {filename}\n")
                f.write(f"Document ID: {doc_id}\n")
                f.write(f"Number of Nanozymes: {num_nanozymes}\n")
                f.write("=" * 70 + "\n\n")
                
                # Write nanozyme name list
                f.write("NANOZYME NAME LIST:\n")
                for i, name in enumerate(names_list, 1):
                    f.write(f"  {i}. {name}\n")
                f.write("\n" + "=" * 70 + "\n\n")
                
                # Write extraction content
                if content:
                    f.write(content)
                else:
                    f.write("No nanozyme parameter information extracted.\n")
            
            timeutils.print_log(f"Results saved to: {txt_path}")
            return txt_path
            
        except Exception as e:
            timeutils.print_log(f"Error saving results: {e}")
            return None


# Keep this function for main.py to call
def extract_and_save_nanozyme(filename, doc_id, nanozyme_names, chat_id=None):
    """
    Extract nanozyme parameters and save results (called by main.py)
    
    Parameters:
    filename: Document filename
    doc_id: RAGFlow document ID
    nanozyme_names: Nanozyme name list
    chat_id: Optional chat ID
    
    Returns:
    str: Saved file path
    """
    extractor = NanozymeExtractor(chat_id)
    
    # Extract parameters
    timeutils.print_log(f"Starting nanozyme parameter extraction from document {doc_id}...")
    content = extractor.extract_nanozyme_parameters_from_list(filename, doc_id, nanozyme_names)
    
    if content:
        # Save results
        saved_path = extractor.save_extraction_results(content, filename, doc_id, nanozyme_names)
        if saved_path:
            timeutils.print_log(f"Extraction completed, results saved")
        else:
            timeutils.print_log(f"Extraction completed but save failed")
        return saved_path
    else:
        timeutils.print_log(f"Failed to extract nanozyme parameters from document {doc_id}")
        return None


if __name__ == "__main__":
    # Simple standalone test
    csv_file_path = "/public/ly/hj/nanozyme_names.csv"
    
    if os.path.exists(csv_file_path):
        timeutils.print_log(f"Test mode: Loading CSV file {csv_file_path}")
        
        # Simple test: read CSV and show first few rows
        try:
            df = pd.read_csv(csv_file_path)
            timeutils.print_log(f"CSV file contains {len(df)} rows")
            timeutils.print_log(f"Column names: {list(df.columns)}")
            
            # Show first 5 rows
            for i in range(min(5, len(df))):
                row = df.iloc[i]
                timeutils.print_log(f"Row {i+1}: {row.to_dict()}")
                
        except Exception as e:
            timeutils.print_log(f"Failed to read CSV: {e}")
    else:
        timeutils.print_log(f"CSV file not found: {csv_file_path}")
        timeutils.print_log("Please check file path")