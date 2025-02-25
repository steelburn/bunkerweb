local ngx = ngx
local cachestore = require "bunkerweb.cachestore"
local class = require "middleclass"
local clusterstore = require "bunkerweb.clusterstore"
local datastore = require "bunkerweb.datastore"
local logger = require "bunkerweb.logger"
local utils = require "bunkerweb.utils"
local plugin = class("plugin")

local ERR = ngx.ERR
local get_phase = ngx.get_phase
local get_variable = utils.get_variable
local get_ctx_obj = utils.get_ctx_obj
local subsystem = ngx.config.subsystem

function plugin:initialize(id, ctx)
	-- Store common, values
	self.id = id
	local is_request = false
	local current_phase = get_phase()
	for _, check_phase in ipairs {
		"set",
		"rewrite",
		"access",
		"content",
		"header_filter",
		"body_filter",
		"log",
		"preread",
	} do
		if current_phase == check_phase then
			is_request = true
			break
		end
	end
	self.is_request = is_request
	-- Store common objects
	self.logger = logger:new(self.id)
	local use_redis, err = get_variable("USE_REDIS", false)
	if not use_redis then
		self.logger:log(ERR, err)
	end
	self.use_redis = use_redis == "yes"
	if self.is_request then
		self.ctx = ctx or ngx.ctx
		self.datastore = get_ctx_obj("datastore", self.ctx) or datastore:new()
		self.cachestore = get_ctx_obj("cachestore", self.ctx) or cachestore:new(use_redis == "yes", self.ctx)
		self.clusterstore = get_ctx_obj("clusterstore", self.ctx) or clusterstore:new()
		self.cachestore_local = get_ctx_obj("cachestore_local", self.ctx) or cachestore:new(false, self.ctx)
	else
		self.datastore = datastore:new()
		self.cachestore = cachestore:new(use_redis == "yes")
		self.clusterstore = clusterstore:new(false)
		self.cachestore_local = cachestore:new(false)
	end
	-- Get metadata
	local metadata, err = self.datastore:get("plugin_" .. id, true)
	if not metadata then
		self.logger:log(ERR, err)
		return
	end
	-- Store variables
	self.variables = {}
	self.multiples = {}
	local value
	for k, v in pairs(metadata.settings) do
		value, err = get_variable(k, v.context == "multisite" and self.is_request)
		if value == nil then
			self.logger:log(ERR, "can't get " .. k .. " variable : " .. err)
		end
		self.variables[k] = value
	end
	-- Is loading
	local is_loading, err = get_variable("IS_LOADING", false)
	if is_loading == nil then
		self.logger:log(ERR, "can't get IS_LOADING variable : " .. err)
	end
	self.is_loading = is_loading == "yes"
	-- Kind of server
	if subsystem == "http" then
		self.kind = "http"
	else
		self.kind = "stream"
	end
end

function plugin:get_id()
	return self.id
end

-- luacheck: ignore 212
function plugin:ret(ret, msg, status, redirect, data)
	return { ret = ret, msg = msg, status = status, redirect = redirect, data = data }
end

return plugin
