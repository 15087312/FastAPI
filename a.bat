@echo off
setlocal enabledelayedexpansion

curl https://api.minimax.io/anthropic/v1/messages ^
  -H "Content-Type: application/json" ^
  -H "Authorization: Bearer sk-api-nBw_xeYGYaaQ5u0G1sZxnmzLMEPXq6T_SGFVU3K6MMipLpQV7KOJ5wKLfQuUyICqGY2TnhxB3TfthTyeOeRua7kyoEvxDWpofQ3nj0o-grny8nDdFy-qoj8" ^
  -d "{\"model\": \"MiniMax-M2.5\", \"messages\":[{\"role\": \"user\", \"content\": \"hi\"}], \"max_tokens\": 10}"