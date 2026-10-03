import sys
import unittest
import json
import xml.etree.ElementTree as ET
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from ingestion.parsers.faa_cfr_parser import (
    normalize_text,
    elem_to_text,
    table_to_markdown,
    parse_faa_part,
    generate_faa_chunks,
    parse_cfr_volume,
)

class TestFAACFRParser(unittest.TestCase):
    
    def test_normalize_text(self):
        raw = "§\u200921.1\u2014Applicability\u2002and\u00a0definitions.\n\n   Extra   spaces.  "
        clean = normalize_text(raw)
        self.assertIn("§ 21.1 - Applicability and definitions.", clean)
        self.assertIn("Extra spaces.", clean)
        
    def test_table_to_markdown(self):
        xml_table = """
        <GPOTABLE COLS="2">
            <BOXHD>
                <CHED H="1">CFR Part</CHED>
                <CHED H="1">OMB Control Number</CHED>
            </BOXHD>
            <ROW>
                <ENT>Part 21</ENT>
                <ENT>2120-0018</ENT>
            </ROW>
        </GPOTABLE>
        """
        elem = ET.fromstring(xml_table)
        md = table_to_markdown(elem)
        self.assertIn("| CFR Part | OMB Control Number |", md)
        self.assertIn("| --- | --- |", md)
        self.assertIn("| Part 21 | 2120-0018 |", md)

    def test_sample_part_parsing(self):
        xml_part = """
        <PART>
            <EAR>Pt. 999</EAR>
            <HD SOURCE="HED">PART 999—TEST AVIATION REGULATION</HD>
            <AUTH>
                <HD SOURCE="HED">Authority:</HD>
                <P>49 U.S.C. 106(f), 44701.</P>
            </AUTH>
            <SOURCE>
                <HD SOURCE="HED">Source:</HD>
                <P>90 FR 1234, Jan. 1, 2025.</P>
            </SOURCE>
            <SUBPART>
                <HD SOURCE="HED">Subpart A—General</HD>
                <SECTION>
                    <SECTNO>§&#x2009;999.1</SECTNO>
                    <SUBJECT>Applicability.</SUBJECT>
                    <P>(a) This part prescribes rules governing test flight operations.</P>
                    <P>(b) All operators must comply.</P>
                </SECTION>
                <SECTION>
                    <SECTNO>§&#x2009;999.2</SECTNO>
                    <SUBJECT>Definitions.</SUBJECT>
                    <P><E T="03">Test Operator</E> means an authorized testing organization.</P>
                    <P><E T="03">Test Aircraft</E> means an aircraft used for testing.</P>
                </SECTION>
            </SUBPART>
        </PART>
        """
        elem = ET.fromstring(xml_part)
        doc = parse_faa_part(elem, "test_vol")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["document_id"], "FAA_14CFR_Part_999")
        self.assertEqual(doc["part_number"], "999")
        self.assertIn("PART 999 - TEST AVIATION REGULATION", doc["title"])
        self.assertEqual(doc["sections_count"], 2)
        
        chunks = generate_faa_chunks(doc)
        # Should have § 999.1 and § 999.2
        self.assertTrue(len(chunks) >= 2)
        
        # Check chunk structure
        c0 = chunks[0]
        self.assertEqual(c0["chunk_id"], "FAA_14CFR_Part_999:sec_999_1")
        self.assertEqual(c0["document_id"], "FAA_14CFR_Part_999")
        self.assertEqual(c0["chunk_type"], "section")
        self.assertIn("14 CFR PART 999 - TEST AVIATION REGULATION", c0["embedding_text"])
        self.assertIn("Subpart A - General", c0["embedding_text"])
        self.assertIn("§ 999.1 Applicability.", c0["embedding_text"])
        self.assertIsNone(c0["previous_chunk_id"])
        self.assertIsNotNone(c0["next_chunk_id"])
        
        # Check metadata
        meta = json.loads(c0["metadata_json"])
        self.assertEqual(meta["source"], "FAA XML")
        self.assertEqual(meta["agency"], "FAA")
        self.assertEqual(meta["cfr_title"], 14)
        self.assertEqual(meta["part"], "999")

    def test_real_faa_vol1_part21(self):
        faa_vol1 = Path("ingestion/data/FAA/CFR-2025-title14-vol1.xml")
        if not faa_vol1.exists():
            self.skipTest("FAA vol1 file not found")
            
        tree = ET.parse(str(faa_vol1))
        part21_elem = None
        for p in tree.findall(".//PART"):
            if "Pt. 21" in (p.findtext("EAR") or ""):
                part21_elem = p
                break
                
        self.assertIsNotNone(part21_elem)
        doc = parse_faa_part(part21_elem, "vol1")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["document_id"], "FAA_14CFR_Part_21")
        self.assertEqual(doc["part_number"], "21")
        
        chunks = generate_faa_chunks(doc)
        self.assertGreater(len(chunks), 100)
        
        # Ensure all chunk_ids are unique
        chunk_ids = [c["chunk_id"] for c in chunks]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)), "Duplicate chunk IDs found!")

if __name__ == "__main__":
    unittest.main()
