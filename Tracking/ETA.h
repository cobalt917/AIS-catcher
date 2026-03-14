/*
	Copyright(c) 2021-2025 jvde.github@gmail.com

	This program is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	This program is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with this program.  If not, see <https://www.gnu.org/licenses/>.
*/

#pragma once

#include <string>
#include <vector>
#include <cmath>

#include "Ships.h"

struct ETAInfo {
	uint32_t mmsi;
	std::string name;
	std::string direction;
	float eta_minutes;
	float cpa_distance;
	float current_distance;
	bool is_approaching;
};

class ETACalculator {
	static float deg2rad(float deg) { return deg * 3.14159265358979323846f / 180.0f; }

public:
	static ETAInfo calculate(const Ship& ship, float station_lat, float station_lon);
	static std::string getDirection(float cog);
};
