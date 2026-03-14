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

#include "ETA.h"
#include "Common.h"

ETAInfo ETACalculator::calculate(const Ship& ship, float station_lat, float station_lon)
{
	ETAInfo info;
	info.mmsi = ship.mmsi;
	info.name = ship.shipname;
	info.is_approaching = false;
	info.eta_minutes = -1;
	info.cpa_distance = -1;
	info.current_distance = -1;
	info.direction = "Unknown";

	// Check for valid position
	if (ship.lat == LAT_UNDEFINED || ship.lon == LON_UNDEFINED ||
		station_lat == LAT_UNDEFINED || station_lon == LON_UNDEFINED)
	{
		return info;
	}

	// Convert positions to local coordinates (nautical miles from station)
	// 1 degree of latitude = 60 nautical miles
	// 1 degree of longitude = 60 * cos(latitude) nautical miles
	float dlat = (ship.lat - station_lat) * 60.0f;
	float dlon = (ship.lon - station_lon) * 60.0f * cos(deg2rad(station_lat));

	float current_dist = sqrt(dlat * dlat + dlon * dlon);
	info.current_distance = current_dist;

	// Check for valid speed and course
	if (ship.speed <= 0 || ship.speed == SPEED_UNDEFINED ||
		ship.cog == COG_UNDEFINED || ship.cog >= 360)
	{
		info.direction = "Stationary";
		info.cpa_distance = current_dist;
		return info;
	}

	info.direction = getDirection(ship.cog);

	// Ship velocity vector (nautical miles per hour = knots)
	float vx = ship.speed * sin(deg2rad(ship.cog));  // East component
	float vy = ship.speed * cos(deg2rad(ship.cog));  // North component

	// Position vector (from station to ship)
	float px = dlon;
	float py = dlat;

	// Time to CPA (hours): t = -(P dot V) / |V|^2
	// This formula finds the time when distance is minimized
	float v_squared = vx * vx + vy * vy;
	if (v_squared < 0.0001f)
	{
		info.cpa_distance = current_dist;
		return info;
	}

	float tcpa_hours = -(px * vx + py * vy) / v_squared;

	// CPA position (where ship will be at time of closest approach)
	float cpa_x = px + vx * tcpa_hours;
	float cpa_y = py + vy * tcpa_hours;
	float cpa_dist = sqrt(cpa_x * cpa_x + cpa_y * cpa_y);

	info.eta_minutes = tcpa_hours * 60.0f;
	info.cpa_distance = cpa_dist;
	info.is_approaching = (tcpa_hours > 0);  // Positive = CPA is in the future

	return info;
}

std::string ETACalculator::getDirection(float cog)
{
	if (cog == COG_UNDEFINED || cog >= 360) return "Unknown";

	// Normalize to 0-360
	while (cog < 0) cog += 360;
	while (cog >= 360) cog -= 360;

	// Determine cardinal direction based on COG
	// COG 0 = North (ship heading north), so from observer's perspective
	// a ship heading north is going away if observer is south of ship
	// We report the direction the ship is heading
	if (cog >= 315 || cog < 45) return "Northbound";
	if (cog >= 45 && cog < 135) return "Eastbound";
	if (cog >= 135 && cog < 225) return "Southbound";
	return "Westbound";
}
