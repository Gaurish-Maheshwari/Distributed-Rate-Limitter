-- Exact sliding window: a sorted set holding one member per accepted request.
-- KEYS[1] zset key
-- ARGV[1] limit | ARGV[2] window ms | ARGV[3] cost | ARGV[4] unique request id
local key    = KEYS[1]
local limit  = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost   = tonumber(ARGV[3])
local uid    = ARGV[4]

local t   = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)

if count + cost > limit then
  -- we may retry once enough of the oldest entries have aged out
  local idx = count + cost - limit - 1
  local retry = window
  local e = redis.call('ZRANGE', key, idx, idx, 'WITHSCORES')
  if e[2] then
    retry = math.max(1, tonumber(e[2]) + window - now)
  end
  return {0, math.max(0, limit - count), retry, retry}
end

for i = 1, cost do
  redis.call('ZADD', key, now, uid .. ':' .. i)
end
redis.call('PEXPIRE', key, window + 1000)

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local reset = math.max(0, tonumber(oldest[2]) + window - now)
return {1, limit - count - cost, 0, reset}
