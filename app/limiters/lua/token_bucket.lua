-- KEYS[1] bucket key
-- ARGV[1] capacity | ARGV[2] refill rate (tokens/sec) | ARGV[3] cost
-- returns {allowed, remaining, retry_after_ms, reset_ms}
local key        = KEYS[1]
local capacity   = tonumber(ARGV[1])
local rate       = tonumber(ARGV[2])
local cost       = tonumber(ARGV[3])

local t   = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)

local data   = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts     = tonumber(data[2])

if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + (elapsed / 1000) * rate)

local allowed, retry = 0, 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry = math.ceil((cost - tokens) / rate * 1000)
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- a bucket that has been idle long enough to refill completely is equivalent to a new one
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000) + 1000)

local reset = math.ceil((capacity - tokens) / rate * 1000)
return {allowed, math.floor(tokens), retry, reset}
