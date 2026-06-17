#!/usr/bin/env python3
"""Run the real edit short with pre-cleaned keywords"""
import os, sys
sys.path.insert(0, os.path.expanduser("~"))

# Monkey-patch the keyword generation to sanitize
import real_edit_short as res
import re

orig_generate = res.generate_script
def patched_generate():
    topic, script, keywords = orig_generate()
    # Clean keywords - remove quotes, special chars
    keywords = [re.sub(r'[^a-zA-Z0-9 ]', '', k).strip() for k in keywords]
    keywords = [k for k in keywords if k]
    if len(keywords) < 5:
        keywords += ["space galaxy", "science nature", "abstract light", "earth planet", "technology future"]
    return topic, script, keywords[:5]

res.generate_script = patched_generate
res.main()
