-- Approximate sliding window: estimate = prev_count * overlap_weight + current_count
-- KEYS[1] key prefix (window index appended)
-- ARGV[1] limit | ARGV[2] window ms | ARGV[3] cost
local prefix = KEYS[1]
local limit  = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost   = tonumber(ARGV[3])

local t   = redis.call('TIME')
local now = t[1] * 1000 + math.floor(t[2] / 1000)

local idx     = math.floor(now / window)
local elapsed = now - idx * window
local reset   = window - elapsed
local weight  = (window - elapsed) / window

local cur_key  = prefix .. ':' .. idx
local prev_key = prefix .. ':' .. (idx - 1)
local cur  = tonumber(redis.call('GET', cur_key) or '0')
local prev = tonumber(redis.call('GET', prev_key) or '0')

local estimate = prev * weight + cur
if estimate + cost > limit then
  local retry = reset
  if prev > 0 then
    local needed = (limit - cur - cost) / prev   -- weight at which the request fits
    if needed >= 0 and needed < weight then
      retry = math.ceil((weight - needed) * window)
    end
  end
  return {0, math.max(0, math.floor(limit - estimate)), math.max(1, retry), reset}
end

cur = redis.call('INCRBY', cur_key, cost)
redis.call('PEXPIRE', cur_key, window * 2 + 1000)
return {1, math.max(0, math.floor(limit - (prev * weight + cur))), 0, reset}
