from openai import OpenAI,RateLimitError
import requests
import time
import random
from typing import Any, Dict

class LLM_model:
    def __init__(self, llm_choice='gpt-4o', llm_key='', temp=None, provider='nebius'):
        self.llm_choice = llm_choice
        self.llm_key = llm_key
        self.use_openai = llm_choice in ['gpt-4o', 'gpt-4', 'gpt-3.5-turbo']
        self.temp = temp
        
        self.backoff_factor =3
        self.jitter_factor = 1

        if provider == 'nscale':
            print('using provider NSCALE')
            self.client = OpenAI(
                base_url="https://inference.api.nscale.com/v1",
                api_key=self.llm_key,
            )
        elif provider == 'huggingface':
            print('using provider HuggingFace')
            self.client = OpenAI(
                base_url="https://router.huggingface.co/v1",
                api_key=self.llm_key,
            )
        elif provider == 'openai':
            print('using provider OpenAI')
            self.client = OpenAI(api_key=self.llm_key)
        else:
            print('using provider NEBIUS')
            self.client = OpenAI(
                base_url="https://api.studio.nebius.com/v1/",
                api_key=self.llm_key,
            )

        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0

        self._snap_prompt = 0
        self._snap_completion = 0
        self._snap_total = 0

    def _record_usage(self, response):
        try:
            usage = getattr(response, "usage", None)
            if usage is None and isinstance(response, dict):
                usage = response.get("usage")
            if usage:
                p = getattr(usage, "prompt_tokens", None) or usage.get("prompt_tokens", 0)
                c = getattr(usage, "completion_tokens", None) or usage.get("completion_tokens", 0)
                t = getattr(usage, "total_tokens", None) or usage.get("total_tokens", (p or 0) + (c or 0))
                self.total_prompt_tokens += int(p or 0)
                self.total_completion_tokens += int(c or 0)
                self.total_tokens += int(t or 0)
        except Exception:
            pass

    def snapshot_usage(self):
        self._snap_prompt = self.total_prompt_tokens
        self._snap_completion = self.total_completion_tokens
        self._snap_total = self.total_tokens

    def usage_since_snapshot(self):
        return {
            "prompt": self.total_prompt_tokens - self._snap_prompt,
            "completion": self.total_completion_tokens - self._snap_completion,
            "total": self.total_tokens - self._snap_total,
        }

    def generate(self, prompt, system_prompt, max_tokens=200):
        if self.use_openai:
            out, resp = self._generate_openai(prompt, system_prompt, max_tokens)
        else:
            out, resp = self._generate_huggingface_chat(prompt, system_prompt, max_tokens)
        self._record_usage(resp)
        return out

    def _extract_text_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    if item.strip():
                        parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                        continue
                    nested = item.get("content")
                    if isinstance(nested, str) and nested.strip():
                        parts.append(nested.strip())
                        continue
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                        continue
                    nested = getattr(item, "content", None)
                    if isinstance(nested, str) and nested.strip():
                        parts.append(nested.strip())
                        continue
            return "\n".join(parts).strip()
        return ""

    def _extract_message_text(self, response: Any) -> str:
        choices = getattr(response, "choices", None)
        if not choices and isinstance(response, dict):
            choices = response.get("choices")
        if not choices:
            return ""

        choice0 = choices[0]
        message = getattr(choice0, "message", None)
        if message is None and isinstance(choice0, dict):
            message = choice0.get("message")

        if message is not None:
            content = getattr(message, "content", None)
            if content is None and isinstance(message, dict):
                content = message.get("content")
            text = self._extract_text_content(content)
            if text:
                return text

            for attr_name in ("reasoning_content", "text", "refusal"):
                alt = getattr(message, attr_name, None)
                if alt is None and isinstance(message, dict):
                    alt = message.get(attr_name)
                text = self._extract_text_content(alt)
                if text:
                    return text

        direct_text = getattr(choice0, "text", None)
        if direct_text is None and isinstance(choice0, dict):
            direct_text = choice0.get("text")
        return self._extract_text_content(direct_text)

    def _generate_openai(self, prompt, system_prompt, max_tokens=200):
        headers = {"Authorization": f"Bearer {self.llm_key}"}
        data = {
            "model": self.llm_choice,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens
        }
        if self.temp is not None:
            data["temperature"] = self.temp

        attempt = 0
        while True:
            response = requests.post(self.api_url, json=data, headers=headers)
            
            if response.status_code == 200:
                j = response.json()
                text = self._extract_message_text(j)
                if text:
                    return text, j
                return "Error: empty model response", j
            
            elif response.status_code == 429:
                sleep_time = self.backoff_factor * min(attempt, 10) * random.random()
                print(f"Rate limit error (HTTP 429). Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                attempt += 1
            
            else:
                return f"Error: {response.status_code}, {response.text}", {"usage": None}


    def _generate_huggingface_chat(self, prompt, system_prompt, max_tokens=200):
        kwargs = dict(
            model=self.llm_choice,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
        )
        if self.temp is not None:
            kwargs["temperature"] = self.temp
            
        attempt = 0
        while True:
            try:
                response = self.client.chat.completions.create(**kwargs)
                text = self._extract_message_text(response)
                if text:
                    return text, response
                return "Error during chat call: empty model response", response
            except RateLimitError:
                sleep_time = self.backoff_factor * min(attempt, 10) * random.random()
                print(f"Rate limit error caught. Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                attempt += 1
            except Exception as e:
                return f"Error during chat call: {str(e)}", {"usage": None}

if __name__ == "__main__":
    pass
