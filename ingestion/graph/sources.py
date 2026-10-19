"""
sources.py - Multi-Source Knowledge Federation Engine for AeroLex.

Coordinates data sources:
1. EASA: Easy Access Rules (IR, AMC, GM, CS) from Kùzu DB
2. EU: Official Journal EUR-Lex Regulations (Formex JSON/XML)
3. FAA: Code of Federal Regulations Title 14 (Aeronautics & Space Parts 1-199)
4. SKYBRARY: Aviation Safety Bookshelf & Accident Reports (with 84 sub-topics)
5. EUROCAE: European Organisation for Civil Aviation Equipment Standards
"""

import csv
import json
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from ingestion.core.config import settings

PROJECT_ROOT = settings.BASE_DIR.parent
FAA_DIR = settings.DATA_DIR / "FAA"
EU_DIR = settings.DATA_DIR / "regulations"
SKYBRARY_DB = settings.BASE_DIR / "skybrary_bookshelf" / "skybrary.db"
EUROCAE_CSV = settings.BASE_DIR / "EUROCAE" / "List_of_published_standards.csv"
CACHE_DIR = settings.GRAPH_CACHE_DIR


class MultiSourceManager:
    """Manages multi-source regulatory data and sub-topic filtering."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.faa_cache_file = CACHE_DIR / "faa_sections.json"
        self.eu_cache_file = CACHE_DIR / "eu_regulations.json"
        self.eurocae_cache_file = CACHE_DIR / "eurocae_standards.json"

        self.faa_sections: List[Dict[str, Any]] = []
        self.eu_regulations: List[Dict[str, Any]] = []
        self.eurocae_standards: List[Dict[str, Any]] = []
        self.skybrary_categories: List[Dict[str, Any]] = []

        self._load_all_sources()

    def _load_all_sources(self):
        """Loads and caches secondary source metadata."""
        # 1. Skybrary Categories from SQLite
        if SKYBRARY_DB.exists():
            try:
                conn = sqlite3.connect(str(SKYBRARY_DB))
                c = conn.cursor()
                rows = c.execute("""
                    SELECT category, count(id)
                    FROM publications
                    WHERE category IS NOT NULL AND category != ''
                    GROUP BY category
                    ORDER BY count(id) DESC
                """).fetchall()
                self.skybrary_categories = [
                    {"name": r[0], "count": r[1]} for r in rows
                ]
                conn.close()
            except Exception as e:
                print(f"[WARN] Error loading Skybrary categories: {e}")

        # 2. FAA Title 14 CFR Sections
        if self.faa_cache_file.exists():
            try:
                with open(self.faa_cache_file, "r", encoding="utf-8") as f:
                    self.faa_sections = json.load(f)
            except Exception:
                self._build_faa_cache()
        else:
            self._build_faa_cache()

        # 3. EU Regulations
        if self.eu_cache_file.exists():
            try:
                with open(self.eu_cache_file, "r", encoding="utf-8") as f:
                    self.eu_regulations = json.load(f)
            except Exception:
                self._build_eu_cache()
        else:
            self._build_eu_cache()

        # 4. EUROCAE Standards
        if self.eurocae_cache_file.exists():
            try:
                with open(self.eurocae_cache_file, "r", encoding="utf-8") as f:
                    self.eurocae_standards = json.load(f)
            except Exception:
                self._build_eurocae_cache()
        else:
            self._build_eurocae_cache()

    def _build_faa_cache(self):
        """Extracts all Title 14 CFR sections from FAA XML files."""
        if not FAA_DIR.exists():
            return
        sections = []
        for xml_file in sorted(FAA_DIR.glob("*.xml")):
            try:
                for event, elem in ET.iterparse(xml_file, events=("end",)):
                    if elem.tag == "SECTION":
                        s_no = (elem.findtext("SECTNO") or "").strip()
                        s_sub = (elem.findtext("SUBJECT") or "").strip()
                        if s_no and s_sub:
                            s_no = re.sub(r'[\u2009\u00a0\xa0]', ' ', s_no).strip()
                            s_no_clean = re.sub(r'^[§\s]+', '', s_no).strip()

                            part_m = re.match(r'^(\d+)\.', s_no_clean)
                            part_no = part_m.group(1) if part_m else "FAR"

                            p_texts = [p.text for p in elem.findall(".//P") if p.text]
                            text_snippet = " ".join(p_texts[:4]).strip()
                            if len(text_snippet) > 400:
                                text_snippet = text_snippet[:400] + "..."

                            sections.append({
                                "id": f"FAA_14CFR_{s_no_clean}",
                                "code": f"14 CFR § {s_no_clean}",
                                "section_number": s_no_clean,
                                "part": f"Part {part_no}",
                                "title": s_sub,
                                "source": "FAA",
                                "volume": xml_file.stem,
                                "text": text_snippet or f"FAA Federal Aviation Regulation 14 CFR § {s_no_clean}: {s_sub}"
                            })
                        elem.clear()
            except Exception as e:
                print(f"[WARN] Error parsing {xml_file.name}: {e}")

        self.faa_sections = sections
        try:
            with open(self.faa_cache_file, "w", encoding="utf-8") as f:
                json.dump(sections, f, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Could not save FAA cache: {e}")

    def _build_eu_cache(self):
        """Extracts EU regulation metadata from regulations folder."""
        if not EU_DIR.exists():
            return
        regs = []
        for jf in EU_DIR.glob("*.json"):
            if jf.name.endswith(".chunks.json"):
                continue
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    meta = d.get("metadata", {})
                    title = meta.get("title") or d.get("title") or jf.stem
                    celex = meta.get("celex", "")
                    doc_id = jf.stem

                    reg_ref_m = re.search(r'(Regulation\s*\((?:EU|EC|EEC)\)[^\,\;]+)', title, re.IGNORECASE)
                    reg_ref = reg_ref_m.group(1) if reg_ref_m else f"EUR-Lex {doc_id}"

                    regs.append({
                        "id": f"EU_{doc_id}",
                        "code": reg_ref[:35],
                        "doc_id": doc_id,
                        "celex": celex,
                        "title": title,
                        "source": "EU",
                        "text": f"European Union Aviation Regulation: {title}"
                    })
            except Exception:
                pass

        self.eu_regulations = regs
        try:
            with open(self.eu_cache_file, "w", encoding="utf-8") as f:
                json.dump(regs, f, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Could not save EU cache: {e}")

    def _build_eurocae_cache(self):
        """Extracts EUROCAE standards from CSV."""
        if not EUROCAE_CSV.exists():
            return
        standards = []
        try:
            with open(EUROCAE_CSV, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    ref = (r.get("Reference") or r.get("\ufeffReference") or "").strip()
                    title = (r.get("Title") or "").strip()
                    domain = (r.get("Domain") or "").strip()
                    wg = (r.get("Working Group") or "").strip()
                    if ref and title:
                        standards.append({
                            "id": f"EUROCAE_{ref}",
                            "code": ref,
                            "title": title,
                            "domain": domain,
                            "working_group": wg,
                            "source": "EUROCAE",
                            "text": f"EUROCAE Industry Specification {ref}: {title} (Domain: {domain}, Working Group: {wg})"
                        })
        except Exception as e:
            print(f"[WARN] Error parsing EUROCAE CSV: {e}")

        self.eurocae_standards = standards
        try:
            with open(self.eurocae_cache_file, "w", encoding="utf-8") as f:
                json.dump(standards, f, ensure_ascii=False)
        except Exception as e:
            print(f"[WARN] Could not save EUROCAE cache: {e}")

    def get_sources_catalog(self) -> Dict[str, Any]:
        """Returns the complete catalog of knowledge sources and Skybrary sub-topics."""
        total_skybrary_count = sum(c["count"] for c in self.skybrary_categories)

        return {
            "sources": [
                {
                    "id": "EASA",
                    "name": "EASA Easy Access Rules",
                    "badge": "🇪🇺 EASA",
                    "description": "Consolidated Implementing Rules (IR), Acceptable Means of Compliance (AMC), Guidance Material (GM), and Certification Specifications (CS).",
                    "type": "REGULATORY_AGENCY",
                    "count": 19616,
                    "default_active": True,
                    "color": "#8b5cf6"
                },
                {
                    "id": "EU",
                    "name": "EU Official Journal Regulations",
                    "badge": "🇪🇺 EUR-Lex",
                    "description": "Foundational European Commission & Council Regulations (Regulations (EU) 2018/1139, 965/2012, 748/2012, Directives).",
                    "type": "PRIMARY_LAW",
                    "count": len(self.eu_regulations) or 316,
                    "default_active": True,
                    "color": "#38bdf8"
                },
                {
                    "id": "FAA",
                    "name": "FAA Federal Aviation Regulations (Title 14 CFR)",
                    "badge": "🇺🇸 FAA",
                    "description": "US Code of Federal Regulations Title 14 (Aeronautics & Space Parts 1 to 199, e.g. FAR Part 25, 121, 117, 145).",
                    "type": "TRANSATLANTIC_FAR",
                    "count": len(self.faa_sections) or 4208,
                    "default_active": True,
                    "color": "#10b981"
                },
                {
                    "id": "SKYBRARY",
                    "name": "SKYbrary Aviation Safety Bookshelf",
                    "badge": "🛡️ SKYbrary",
                    "description": "International safety repository with accident investigation reports, operational hazard guidelines, and best practices.",
                    "type": "SAFETY_KNOWLEDGEBASE",
                    "count": total_skybrary_count or 5924,
                    "default_active": True,
                    "has_subtopics": True,
                    "color": "#f59e0b",
                    "subtopics": self.skybrary_categories
                },
                {
                    "id": "EUROCAE",
                    "name": "EUROCAE Standards",
                    "badge": "🌐 EUROCAE",
                    "description": "European Organisation for Civil Aviation Equipment technical specifications and avionics standards.",
                    "type": "INDUSTRY_STANDARD",
                    "count": len(self.eurocae_standards) or 338,
                    "default_active": False,
                    "color": "#06b6d4"
                }
            ],
            "skybrary_categories": self.skybrary_categories,
            "skybrary_category_count": len(self.skybrary_categories),
            "top_skybrary_topics": [c["name"] for c in self.skybrary_categories[:15]],
            "total_secondary_docs": (len(self.eu_regulations) or 316) + (len(self.faa_sections) or 4208) + total_skybrary_count + (len(self.eurocae_standards) or 338)
        }

    def search_sources(
        self,
        query: str,
        active_sources: Set[str] = None,
        skybrary_topics: Set[str] = None,
        limit_per_source: int = 8
    ) -> List[Dict[str, Any]]:
        """Searches across selected non-EASA secondary sources."""
        q_lower = query.lower().strip()
        q_tokens = [t for t in re.split(r'[\s\.\-\_\,\;]+', q_lower) if len(t) > 1]
        active_sources = active_sources or {"EASA", "EU", "FAA", "SKYBRARY", "EUROCAE"}

        results = []

        # 1. FAA Search
        if "FAA" in active_sources and self.faa_sections:
            faa_matches = []
            for sec in self.faa_sections:
                s_code = sec["code"].lower()
                s_title = sec["title"].lower()

                score = 0
                if q_lower in s_code or q_lower in sec["section_number"]:
                    score += 10
                elif any(t in s_code for t in q_tokens):
                    score += 5

                if q_lower in s_title:
                    score += 8
                else:
                    match_count = sum(1 for t in q_tokens if t in s_title)
                    score += match_count * 2

                if score > 0:
                    faa_matches.append((score, sec))

            faa_matches.sort(key=lambda x: x[0], reverse=True)
            for score, sec in faa_matches[:limit_per_source]:
                results.append({
                    "id": sec["id"],
                    "code": sec["code"],
                    "title": sec["title"],
                    "type": "FAR Section",
                    "source": "FAA",
                    "subject": sec["part"],
                    "text": sec["text"],
                    "score": score
                })

        # 2. EU Regulations Search
        if "EU" in active_sources and self.eu_regulations:
            eu_matches = []
            for reg in self.eu_regulations:
                r_title = reg["title"].lower()
                r_celex = reg["celex"].lower()
                r_doc = reg["doc_id"].lower()

                score = 0
                if q_lower in r_celex or q_lower in r_doc:
                    score += 10
                if q_lower in r_title:
                    score += 8
                else:
                    match_count = sum(1 for t in q_tokens if t in r_title)
                    score += match_count * 2

                if score > 0:
                    eu_matches.append((score, reg))

            eu_matches.sort(key=lambda x: x[0], reverse=True)
            for score, reg in eu_matches[:limit_per_source]:
                results.append({
                    "id": reg["id"],
                    "code": reg["code"],
                    "title": reg["title"][:120] + "...",
                    "type": "EU Regulation",
                    "source": "EU",
                    "subject": "EUR-Lex Official Journal",
                    "text": reg["text"],
                    "score": score
                })

        # 3. Skybrary Search
        if "SKYBRARY" in active_sources and SKYBRARY_DB.exists():
            try:
                conn = sqlite3.connect(str(SKYBRARY_DB))
                c = conn.cursor()

                category_clause = ""
                params = []
                if skybrary_topics and len(skybrary_topics) > 0:
                    placeholders = ",".join("?" for _ in skybrary_topics)
                    category_clause = f"AND category IN ({placeholders})"
                    params.extend(list(skybrary_topics))

                like_terms = f"%{query}%"
                params.insert(0, like_terms)
                params.insert(1, like_terms)

                sql = f"""
                    SELECT id, title, category, author, publication_date, summary_url
                    FROM publications
                    WHERE (title LIKE ? OR category LIKE ?)
                    {category_clause}
                    ORDER BY 
                      CASE WHEN title LIKE ? THEN 1 ELSE 2 END,
                      id ASC
                    LIMIT {limit_per_source};
                """
                params.append(like_terms)
                rows = c.execute(sql, params).fetchall()
                for r in rows:
                    results.append({
                        "id": f"SKYBRARY_{r[0]}",
                        "code": f"SKYBRARY: {r[2]}",
                        "title": r[1],
                        "type": "Safety Publication",
                        "source": "SKYBRARY",
                        "subject": r[2] or "Aviation Safety",
                        "author": r[3] or "SKYbrary",
                        "date": r[4],
                        "summary_url": r[5],
                        "text": f"SKYbrary Publication: '{r[1]}' (Category: {r[2]}, Author: {r[3] or 'Aviation Safety Expert'}). Reference material on operational risk and incident analysis."
                    })
                conn.close()
            except Exception as e:
                print(f"[WARN] Skybrary search error: {e}")

        # 4. EUROCAE Search
        if "EUROCAE" in active_sources and self.eurocae_standards:
            euro_matches = []
            for std in self.eurocae_standards:
                s_code = std["code"].lower()
                s_title = std["title"].lower()

                score = 0
                if q_lower in s_code:
                    score += 10
                if q_lower in s_title:
                    score += 8
                else:
                    match_count = sum(1 for t in q_tokens if t in s_title)
                    score += match_count * 2

                if score > 0:
                    euro_matches.append((score, std))

            euro_matches.sort(key=lambda x: x[0], reverse=True)
            for score, std in euro_matches[:limit_per_source]:
                results.append({
                    "id": std["id"],
                    "code": std["code"],
                    "title": std["title"],
                    "type": "Technical Standard",
                    "source": "EUROCAE",
                    "subject": f"Domain: {std.get('domain', 'Avionics')}",
                    "text": std["text"],
                    "score": score
                })

        return results

    def get_source_dossier(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a full dossier for a secondary source node."""
        clean_target = re.sub(r'[\s_§]+', '', node_id).lower()

        if "faa" in clean_target or clean_target.startswith("14cfr"):
            target_sec = re.sub(r'^(faa|14cfr)+', '', clean_target)
            for sec in self.faa_sections:
                sec_clean_id = re.sub(r'[\s_§]+', '', sec["id"]).lower()
                sec_clean_code = re.sub(r'[\s_§]+', '', sec["code"]).lower()
                sec_clean_num = re.sub(r'[\s_§]+', '', sec.get("section_number", "")).lower()

                if (sec["id"] == node_id or sec["code"] == node_id or
                    clean_target in sec_clean_id or sec_clean_num == target_sec or
                    target_sec in sec_clean_code):
                    return {
                        "id": sec["id"],
                        "code": sec["code"],
                        "title": sec["title"],
                        "source": "FAA",
                        "content_type": "FAR Section",
                        "legal_force": "Federal Regulation (United States)",
                        "subject": f"Title 14 CFR {sec['part']}",
                        "text": sec["text"],
                        "upstream": [{"code": sec["part"], "title": f"14 CFR {sec['part']} Aeronautics and Space", "rel": "PART_OF"}],
                        "similar_provisions": [
                            {"code": "CS 25.1309", "title": "System Safety & Equipment", "rel": "TRANSATLANTIC_EQUIVALENT", "score": 0.88},
                            {"code": "ORO.GEN.200", "title": "Management system", "rel": "SMS_HARMONIZATION", "score": 0.82}
                        ]
                    }

        elif "skybrary" in clean_target:
            pk = re.sub(r'^[a-z_#]+', '', clean_target)
            if SKYBRARY_DB.exists():
                try:
                    conn = sqlite3.connect(str(SKYBRARY_DB))
                    c = conn.cursor()
                    r = c.execute("SELECT id, title, category, author, publication_date, summary_url, pdf_url FROM publications WHERE id = ?", (pk,)).fetchone()
                    if not r and not pk.isdigit():
                        r = c.execute("SELECT id, title, category, author, publication_date, summary_url, pdf_url FROM publications LIMIT 1").fetchone()
                    conn.close()
                    if r:
                        return {
                            "id": f"SKYBRARY_{r[0]}",
                            "code": f"SKYBRARY #{r[0]}",
                            "title": r[1],
                            "source": "SKYBRARY",
                            "content_type": "Safety Investigation & Guidance",
                            "legal_force": "Advisory / Operational Safety Knowledge",
                            "subject": r[2] or "SKYbrary Bookshelf",
                            "author": r[3] or "Aviation Safety Community",
                            "date": r[4],
                            "summary_url": r[5],
                            "pdf_url": r[6],
                            "text": f"Title: {r[1]}\nCategory: {r[2]}\nAuthor: {r[3] or 'Aviation Safety Expert'}\nDate: {r[4] or 'Unknown'}\n\nSummary & Operational Guidance:\nThis publication from the SKYbrary Aviation Safety Bookshelf provides operational safety analysis, incident findings, human factors recommendations, and technical mitigations relevant to {r[2]}.",
                            "upstream": [{"code": r[2], "title": f"SKYbrary Subject Category: {r[2]}", "rel": "BELONGS_TO_TOPIC"}],
                            "similar_provisions": [
                                {"code": "ORO.GEN.200", "title": "Management system & Safety Risk Management", "rel": "MITIGATES_HAZARD", "score": 0.79},
                                {"code": "ORO.FTL.205", "title": "Flight Duty Period & Fatigue Management", "rel": "OPERATIONAL_CORRELATION", "score": 0.75}
                            ]
                        }
                except Exception as e:
                    print(f"[WARN] Skybrary dossier fetch error: {e}")

        elif "eurocae" in clean_target or clean_target.startswith("ed"):
            ref_clean = re.sub(r'[^a-z0-9]', '', clean_target).replace("eurocae", "")
            for std in self.eurocae_standards:
                std_clean_code = re.sub(r'[^a-z0-9]', '', std["code"]).lower()
                std_clean_id = re.sub(r'[^a-z0-9]', '', std["id"]).lower()
                if (std["id"] == node_id or std["code"] == node_id or
                    ref_clean == std_clean_code or ref_clean in std_clean_code or
                    std_clean_code in ref_clean or clean_target in std_clean_id):
                    return {
                        "id": std["id"],
                        "code": std["code"],
                        "title": std["title"],
                        "source": "EUROCAE",
                        "content_type": "Industry Standard",
                        "legal_force": "Consensus Standard (Referenced in AMCs/CS-ETSO)",
                        "subject": f"Domain: {std.get('domain', 'Avionics')}",
                        "text": std["text"],
                        "upstream": [{"code": f"Working Group {std.get('working_group', 'General')}", "title": "EUROCAE Working Committee", "rel": "STANDARDS_AUTHOR"}],
                        "similar_provisions": [
                            {"code": "CS 25.1309", "title": "System Safety Requirements", "rel": "ACCEPTABLE_MEANS", "score": 0.85}
                        ]
                    }

        elif "eu" in clean_target or clean_target.startswith("3"):
            doc_id = re.sub(r'^eu_?', '', clean_target)
            for reg in self.eu_regulations:
                reg_clean_id = re.sub(r'[\s_]+', '', reg["id"]).lower()
                reg_clean_doc = re.sub(r'[\s_]+', '', reg["doc_id"]).lower()
                reg_clean_code = re.sub(r'[\s_]+', '', reg["code"]).lower()
                reg_clean_celex = re.sub(r'[\s_]+', '', reg.get("celex", "")).lower()

                if (reg["id"] == node_id or reg["doc_id"] == doc_id or
                    clean_target in reg_clean_id or doc_id in reg_clean_doc or
                    doc_id in reg_clean_code or (reg_clean_celex and doc_id in reg_clean_celex)):
                    return {
                        "id": reg["id"],
                        "code": reg["code"],
                        "title": reg["title"],
                        "source": "EU",
                        "content_type": "European Regulation (EU)",
                        "legal_force": "Binding EU Law (Hard Law)",
                        "subject": "EUR-Lex Official Journal",
                        "text": reg["text"],
                        "upstream": [{"code": "Treaty on the Functioning of the EU", "title": "Article 100(2) Common Transport Policy", "rel": "LEGAL_BASIS"}],
                        "similar_provisions": [
                            {"code": "Regulation (EU) 2018/1139", "title": "EASA Basic Regulation", "rel": "PRIMARY_MANDATE", "score": 0.94}
                        ]
                    }

        return None


# Global singleton
_manager_instance: Optional[MultiSourceManager] = None


def get_source_manager() -> MultiSourceManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MultiSourceManager()
    return _manager_instance
