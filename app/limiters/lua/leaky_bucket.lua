-- Leaky bucket as a meter: each request adds `cost` to the level, level drains at `rate`/sec.
-- KEYS[1] bucket key
-- ARGV[1] capacity | ARGV[2] leak rate (units/sec) | ARGV[3] cost
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])

local t   = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)

local data  = redis.call('HMGET', key, 'level', 'ts')
local level = tonumber(data[1]) or 0
local ts    = tonumber(data[2]) or now

local elapsed = math.max(0, now - ts)
level = math.max(0, level - (elapsed / 1000) * rate)

local allowed, retry = 0, 0
if level + cost <= capacity then
  level = level + cost
  allowed = 1
else
  retry = math.ceil((level + cost - capacity) / rate * 1000)
end

redis.call('HSET', key, 'level', level, 'ts', now)
redis.call('PEXPIRE', key, math.ceil(capacity / rate * 1000) + 1000)

local reset = math.ceil(level / rate * 1000)
return {allowed, math.floor(capacity - level), retry, reset}
