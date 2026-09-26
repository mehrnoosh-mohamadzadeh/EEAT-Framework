"""
تست‌های واحد utils/json_ld_utils.py — هر سه الگوی رایج JSON-LD که
سایت‌های واقعی استفاده می‌کنند.
"""

from utils.json_ld_utils import flatten_json_ld_blocks


class TestFlattenJsonLdBlocks:

    def test_plain_dict_block_passed_through(self):
        blocks = [{"@type": "Article", "headline": "X"}]
        result = flatten_json_ld_blocks(blocks)
        assert result == [{"@type": "Article", "headline": "X"}]

    def test_graph_wrapped_block_is_unwrapped(self):
        """الگوی رایج Yoast SEO: {"@graph": [...]}"""
        blocks = [{"@graph": [
            {"@type": "Organization", "name": "X"},
            {"@type": "Person", "name": "Y"},
        ]}]
        result = flatten_json_ld_blocks(blocks)
        assert {"@type": "Organization", "name": "X"} in result
        assert {"@type": "Person", "name": "Y"} in result
        assert len(result) == 2

    def test_bare_array_block_is_unwrapped(self):
        """
        رگرسیون: بعضی سایت‌ها به‌جای @graph، مستقیم یک آرایه‌ی JSON
        خام در تگ script می‌گذارند. نسخه‌ی اول این حالت را کامل
        نادیده می‌گرفت (لیست خالی برمی‌گرداند).
        """
        blocks = [[
            {"@type": "Organization", "name": "X"},
            {"@type": "Article", "dateModified": "2024-01-01"},
        ]]
        result = flatten_json_ld_blocks(blocks)
        assert len(result) == 2
        assert {"@type": "Organization", "name": "X"} in result

    def test_mixed_blocks_all_handled_together(self):
        """ترکیبی از هر سه الگو در یک صفحه باید همه با هم درست پردازش شوند."""
        blocks = [
            {"@type": "Article", "headline": "A"},
            {"@graph": [{"@type": "Person", "name": "B"}]},
            [{"@type": "Organization", "name": "C"}],
        ]
        result = flatten_json_ld_blocks(blocks)
        types_found = {item["@type"] for item in result}
        assert types_found == {"Article", "Person", "Organization"}

    def test_invalid_or_empty_input_does_not_crash(self):
        assert flatten_json_ld_blocks([]) == []
        assert flatten_json_ld_blocks(["not a dict", 123, None]) == []
