# -*- coding: utf-8 -*-
"""
PDF OCR + 本地 Qwen2-VL 模型分析
用于纳米酶论文全文 OCR 和图像内容分析
使用本地部署的 Qwen2-VL-7B-Instruct 模型进行图片深度分析
"""

import base64
import json
import os
import re
import requests
from pathlib import Path
from tqdm import tqdm
from typing import List, Dict, Optional
import warnings
import logging
from PIL import Image
import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration

# 禁用警告
warnings.filterwarnings("ignore", category=UserWarning)
logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

# ================= 1. 配置区 =================

# OCR API 配置
API_URL = ""
TOKEN = ""

# 输入/输出路径
# 这里可以根据你的纳米酶 PDF 文件夹路径自行修改
PDF_SOURCE_DIR = "/data/pdfs"
OUTPUT_ROOT = "/data/ocr_results_output_api"

# Qwen2-VL 模型路径
QWEN_VL_PATH = "/data/models--Qwen--Qwen2-VL-7B-Instruct"

# VL 分析配置
VL_CONFIG = {
    "enabled": True,   # 是否启用 VL 分析
    "batch_size": 1,   # 批量处理大小，建议为 1 以节省显存
}

# ================= 2. 纳米酶图像分析提示词 =================

VL_PROMPT_NANOZYME = """This image is from a scientific paper about nanozymes. Please provide a detailed and technical analysis.

1. **Figure Type**:
   - Identify the type of figure, such as graph, chart, microscopy image, schematic diagram, catalytic mechanism, molecular structure, kinetic plot, material characterization image, or reaction scheme.

2. **Nanozyme Materials**:
   - Identify all nanozyme names or material names shown in the image.
   - Pay attention to nanoparticles, nanosheets, nanorods, nanoflowers, metal oxides, metal sulfides, carbon-based nanozymes, MOFs, single-atom nanozymes, doped materials, composites, and surface-modified nanozymes.
   - If different nanozymes, control samples, modified samples, or composite structures are compared, clearly distinguish them.

3. **Enzyme-like Activity Classification**:
   - Determine whether the figure is related to any of the following nanozyme activities:
     - CAT: catalase-like activity
     - HYL: hydrolase-like activity
     - OXD: oxidase-like activity
     - POD: peroxidase-like activity
     - SOD: superoxide dismutase-like activity
   - If multiple enzyme-like activities are involved, list all of them.
   - Identify the reaction system, substrates, products, or indicators if visible.

4. **Elemental Composition and Chemical Information**:
   - Extract any visible elemental composition, chemical formula, doping element, functional group, or surface coating information.
   - Pay special attention to whether the nanozyme contains the following elements:
     O, N, P, S, Si, Se, B, F, Cl, Br, I.
   - If oxidation states are shown, such as Fe2+/Fe3+, Ce3+/Ce4+, Mn3+/Mn4+, Co2+/Co3+, identify them clearly.
   - If XPS, EDS, elemental mapping, XRD, FTIR, Raman, or UV-vis data are shown, summarize the key information.

5. **Physical Properties**:
   - Extract morphology or shape information, such as sphere, nanoparticle, nanosheet, nanorod, nanoflower, cube, hollow structure, porous structure, or core-shell structure.
   - Extract particle size or scale bar information in nm if visible.
   - Extract surface treatment or functionalization information, such as PEG, PVP, citrate, polymer coating, antibody, aptamer, biomolecule, or ligand modification.
   - Identify dispersion medium if shown, such as water, PBS, buffer, ethanol, or biological medium.

6. **Enzymatic and Kinetic Properties**:
   - Extract optimal pH if shown.
   - Extract optimal reaction temperature in °C if shown.
   - Extract substrate names, such as TMB, H2O2, ABTS, OPD, dopamine, superoxide, or other substrates.
   - Extract kinetic parameters if shown:
     - Km
     - Vmax
     - Kcat
   - Include units exactly as shown in the image. If possible, clarify whether Km is in mM, Vmax is in μM s−1, and Kcat is in s−1.

7. **Data and Measurements**:
   - Extract all numerical values, axis labels, units, legends, sample labels, and experimental conditions.
   - Describe trends, such as increasing activity, decreasing activity, higher catalytic efficiency, better stability, pH-dependent activity, temperature-dependent activity, or concentration-dependent kinetics.
   - For graphs, explain the x-axis, y-axis, curve meaning, and comparison groups.

8. **Labels and Annotations**:
   - List all important visible text labels, legends, captions, arrows, highlighted regions, and symbols.
   - Explain color coding or symbols if they correspond to different nanozymes, substrates, treatments, or activities.

9. **Scientific Insights for Data Extraction**:
   - Explain what conclusion or finding this figure supports.
   - Identify which information may be useful for extracting structured nanozyme parameters.
   - Focus on information corresponding to:
     Nanozyme Name, Classification, elemental composition, metal oxidation state, shape, size, surface treatment, dispersion medium, optimal pH, optimal temperature, substrate, Km, Vmax, and Kcat.

Please be thorough and technical in your analysis, as this output will be used for academic nanozyme data extraction.
"""


# ================= 3. Qwen2-VL 模型加载 =================

class Qwen2VLAnalyzer:
    """Qwen2-VL 图片分析器"""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self.model = None
        self.processor = None
        self._load_model()

    def _load_model(self):
        """加载 Qwen2-VL 模型"""
        if not Path(self.model_path).exists():
            print(f"❌ 模型路径不存在: {self.model_path}")
            return

        print(f"🚀 正在加载 Qwen2-VL-7B 模型...")
        print(f"   路径: {self.model_path}")

        try:
            self.processor = AutoProcessor.from_pretrained(
                self.model_path,
                trust_remote_code=True
            )

            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_path,
                torch_dtype=torch.bfloat16,
                device_map="auto",
                trust_remote_code=True
            ).eval()

            print(f"✅ Qwen2-VL-7B 模型加载完成!")

            if torch.cuda.is_available():
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                print(f"   GPU: {torch.cuda.get_device_name(0)}")
                print(f"   显存: {gpu_memory:.1f} GB")

        except Exception as e:
            print(f"❌ Qwen2-VL-7B 加载失败: {e}")
            self.model = None
            self.processor = None

    def is_available(self) -> bool:
        """检查模型是否可用"""
        return self.model is not None and self.processor is not None

    def analyze_image(self, image_path: str, prompt: str = VL_PROMPT_NANOZYME) -> str:
        """
        分析单张图片

        Args:
            image_path: 图片路径
            prompt: 分析提示词

        Returns:
            分析结果文本
        """
        if not self.is_available():
            return "[VL模型未加载]"

        try:
            image = Image.open(image_path).convert("RGB")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]

            text = self.processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            inputs = self.processor(
                text=[text],
                images=[image],
                padding=True,
                return_tensors="pt"
            )

            inputs = inputs.to(self.model.device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=1024,
                    do_sample=False
                )

            generated_ids_trimmed = [
                out_ids[len(in_ids):]
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]

            output_text = self.processor.batch_decode(
                generated_ids_trimmed,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False
            )[0]

            return output_text.strip()

        except Exception as e:
            return f"[分析失败: {str(e)}]"

    def analyze_batch(self, image_paths: List[str], prompt: str = VL_PROMPT_NANOZYME) -> Dict[str, str]:
        """
        批量分析图片

        Args:
            image_paths: 图片路径列表
            prompt: 分析提示词

        Returns:
            字典，键为图片路径，值为分析结果
        """
        results = {}

        for img_path in tqdm(image_paths, desc="🔍 VL 模型分析中", unit="张"):
            results[img_path] = self.analyze_image(img_path, prompt)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        return results


# ================= 4. OCR 处理功能 =================

def process_single_pdf_api(
        pdf_path: str,
        output_base_dir: str,
        vl_analyzer: Optional[Qwen2VLAnalyzer] = None
):
    """
    处理单个 PDF 文件：OCR + VL 分析

    Args:
        pdf_path: PDF 文件路径
        output_base_dir: 输出根目录
        vl_analyzer: Qwen2-VL 分析器实例
    """
    pdf_file = Path(pdf_path)
    title = pdf_file.stem

    pdf_output_dir = Path(output_base_dir) / title
    final_md_path = pdf_output_dir / f"{title}_ocr_result.md"
    vl_analysis_path = pdf_output_dir / f"{title}_vl_analysis.json"

    if final_md_path.exists():
        print(f"⏩ 已跳过: {title} (结果文件已存在)")
        return

    os.makedirs(pdf_output_dir, exist_ok=True)

    # ===== 步骤 1: OCR 处理 =====
    print(f"📄 [1/3] OCR 处理: {title}")

    with open(pdf_path, "rb") as file:
        file_data = base64.b64encode(file.read()).decode("ascii")

    headers = {
        "Authorization": f"token {TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "file": file_data,
        "fileType": 0,
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useChartRecognition": True,
    }

    response = requests.post(API_URL, json=payload, headers=headers)

    if response.status_code != 200:
        print(f"❌ OCR API 请求失败，状态码: {response.status_code}")
        return

    result = response.json().get("result", {})
    layout_results = result.get("layoutParsingResults", [])

    # ===== 步骤 2: 保存 OCR 结果和图片 =====
    print(f"💾 [2/3] 保存 OCR 结果和图片")

    combined_markdown = []
    all_images = []
    image_to_page_text_map = {}

    for i, res in enumerate(layout_results):
        page_text = res.get("markdown", {}).get("text", "")

        combined_markdown.append(f"\n{'=' * 80}")
        combined_markdown.append(f"PAGE {i + 1}")
        combined_markdown.append(f"{'=' * 80}\n")

        images_dict = res.get("markdown", {}).get("images", {})

        for img_rel_path, img_url in images_dict.items():
            full_img_path = pdf_output_dir / img_rel_path
            os.makedirs(full_img_path.parent, exist_ok=True)

            try:
                img_data = requests.get(img_url).content
                with open(full_img_path, "wb") as f:
                    f.write(img_data)

                all_images.append(str(full_img_path))

                image_to_page_text_map[str(full_img_path)] = {
                    "page_index": i,
                    "rel_path": img_rel_path
                }

                print(f"  ✓ 下载: {img_rel_path}")

            except Exception as e:
                print(f"  ⚠ 图片下载失败 ({img_rel_path}): {e}")

        combined_markdown.append(page_text)

        out_images = res.get("outputImages", {})

        for img_name, img_url in out_images.items():
            out_img_path = pdf_output_dir / f"detection_{img_name}_page{i + 1}.jpg"

            try:
                img_data = requests.get(img_url).content
                with open(out_img_path, "wb") as f:
                    f.write(img_data)

            except Exception as e:
                print(f"  ⚠ 检测图下载失败: {e}")

    # ===== 步骤 3: Qwen2-VL 模型分析并插入到对应位置 =====
    vl_results = {}

    if vl_analyzer and vl_analyzer.is_available() and all_images:
        print(f"🤖 [3/3] Qwen2-VL 模型分析 ({len(all_images)} 张图片)")

        vl_results = vl_analyzer.analyze_batch(all_images, VL_PROMPT_NANOZYME)

        with open(vl_analysis_path, "w", encoding="utf-8") as f:
            json.dump(vl_results, f, ensure_ascii=False, indent=2)

        print(f"  ✓ VL 分析结果已保存: {vl_analysis_path.name}")

        final_markdown = []

        for i, res in enumerate(layout_results):
            final_markdown.append(f"\n{'=' * 80}")
            final_markdown.append(f"PAGE {i + 1}")
            final_markdown.append(f"{'=' * 80}\n")

            page_text = res.get("markdown", {}).get("text", "")
            page_lines = page_text.split("\n")

            for line in page_lines:
                final_markdown.append(line)

                if 'src="imgs/' in line or 'src="images/' in line:
                    match = re.search(r'src="(imgs/[^"]+)"', line)

                    if not match:
                        match = re.search(r'src="(images/[^"]+)"', line)

                    if match:
                        img_rel_path = match.group(1)
                        full_img_path = str(pdf_output_dir / img_rel_path)

                        if full_img_path in vl_results:
                            analysis = vl_results[full_img_path]
                            img_filename = Path(img_rel_path).name

                            final_markdown.append(f"\n**🔍 VL分析 ({img_filename}):**\n")
                            final_markdown.append(f"<blockquote>\n{analysis}\n</blockquote>\n")

        combined_markdown = final_markdown

    else:
        print(f"⏭️  [3/3] 跳过 VL 分析 (模型未加载或无图片)")

    final_md_path.write_text("\n".join(combined_markdown), encoding="utf-8")

    stats = f"""
✅ 处理完成: {title}
   📄 页数: {len(layout_results)}
   🖼️  图片: {len(all_images)}
   🤖 VL分析: {'是 (' + str(len(vl_results)) + '张)' if vl_results else '否'}
   📝 输出: {final_md_path.name}
"""
    print(stats)


def batch_process_folder_api(
        input_dir: str,
        output_base_dir: str,
        vl_analyzer: Optional[Qwen2VLAnalyzer] = None
):
    """
    批量处理文件夹中的所有 PDF

    Args:
        input_dir: 输入目录
        output_base_dir: 输出根目录
        vl_analyzer: Qwen2-VL 分析器实例
    """
    input_path = Path(input_dir)
    pdf_files = list(input_path.glob("*.pdf"))

    if not pdf_files:
        print(f"⚠ 未在 {input_dir} 找到 PDF 文件")
        return

    print(f"\n{'=' * 80}")
    print(f"🚀 批量处理开始")
    print(f"{'=' * 80}")
    print(f"📁 输入目录: {input_dir}")
    print(f"📁 输出目录: {output_base_dir}")
    print(f"📄 文件数量: {len(pdf_files)}")
    print(f"🤖 VL 分析: {'启用 (Qwen2-VL-7B)' if vl_analyzer and vl_analyzer.is_available() else '禁用'}")
    print(f"{'=' * 80}\n")

    for idx, pdf_file in enumerate(pdf_files, 1):
        title = pdf_file.stem
        target_folder = Path(output_base_dir) / title

        if target_folder.exists() and (target_folder / f"{title}_ocr_result.md").exists():
            print(f"[{idx}/{len(pdf_files)}] ⏩ 已跳过: {title} (已处理)")
            continue

        print(f"\n{'=' * 80}")
        print(f"[{idx}/{len(pdf_files)}] 处理: {pdf_file.name}")
        print(f"{'=' * 80}")

        try:
            process_single_pdf_api(str(pdf_file), output_base_dir, vl_analyzer)

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    print(f"\n{'=' * 80}")
    print(f"✅ 批量处理完成!")
    print(f"{'=' * 80}\n")


# ================= 5. 主程序入口 =================

def main():
    """主程序"""
    vl_analyzer = None

    if VL_CONFIG["enabled"]:
        print("=" * 80)
        vl_analyzer = Qwen2VLAnalyzer(QWEN_VL_PATH)
        print("=" * 80 + "\n")

        if not vl_analyzer.is_available():
            print("⚠ Qwen2-VL 模型加载失败，将仅进行 OCR 处理\n")
            response = input("是否继续仅进行 OCR 处理? (y/n): ")

            if response.lower() != "y":
                return

    batch_process_folder_api(
        input_dir=PDF_SOURCE_DIR,
        output_base_dir=OUTPUT_ROOT,
        vl_analyzer=vl_analyzer
    )


if __name__ == "__main__":
    main()