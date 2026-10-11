-- KEYS[1] key prefix (window index is appended; same hash tag => same cluster slot)
-- ARGV[1] limit | ARGV[2] window ms | ARGV[3] cost
local prefix = KEYS[1]
local limit  = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost   = tonumber(ARGV[3])

local t   = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)

local idx   = math.floor(now / window)
local key   = prefix .. ':' .. idx
local reset = (idx + 1) * window - now

local count = tonumber(redis.call('GET', key) or '0')
if count + cost > limit then
  return {0, math.max(0, limit - count), reset, reset}
end

count = redis.call('INCRBY', key, cost)
if count == cost then
  redis.call('PEXPIRE', key, window + 1000)
end
return {1, limit - count, 0, reset}
