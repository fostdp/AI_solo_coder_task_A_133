import math
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class FlueParams:
    flue_diameter: float = 0.05
    flue_length: float = 0.8
    flue_area: float = 0.0
    flue_cross_section_area: float = 0.0

    def __post_init__(self):
        self.flue_cross_section_area = math.pi * (self.flue_diameter / 2) ** 2
        self.flue_area = math.pi * self.flue_diameter * self.flue_length


class FlueFluidSimulator:
    """
    烟道流体仿真模型
    基于层流和自然对流理论，计算烟气在烟道内的流动和冷却沉降
    """

    def __init__(self, params: Optional[FlueParams] = None):
        self.params = params or FlueParams()

        self.g = 9.81
        self.k_air = 0.026
        self.cp_air = 1005.0
        self.rho_air_ref = 1.204
        self.mu_air_ref = 1.81e-5
        self.T_ref = 293.15

    def _air_viscosity(self, T: float) -> float:
        T_kelvin = T + 273.15
        S = 110.4
        mu_ref = 1.716e-5
        T_ref_suth = 273.15
        return mu_ref * (T_kelvin / T_ref_suth) ** 1.5 * (T_ref_suth + S) / (T_kelvin + S)

    def _air_density(self, T: float, P: float = 101325.0) -> float:
        T_kelvin = T + 273.15
        R_air = 287.0
        return P / (R_air * T_kelvin)

    def _air_thermal_conductivity(self, T: float) -> float:
        T_kelvin = T + 273.15
        return 0.026 * (T_kelvin / 300.0) ** 0.8

    def _air_specific_heat(self, T: float) -> float:
        T_kelvin = T + 273.15
        return 1005.0 + 0.1 * (T_kelvin - 300.0)

    def calculate_reynolds(self, velocity: float, T_flue: float, T_ambient: float = 25.0) -> float:
        T_avg = (T_flue + T_ambient) / 2
        rho = self._air_density(T_avg)
        mu = self._air_viscosity(T_avg)
        Re = rho * velocity * self.params.flue_diameter / mu
        return max(1.0, Re)

    def calculate_prandtl(self, T_flue: float, T_ambient: float = 25.0) -> float:
        T_avg = (T_flue + T_ambient) / 2
        mu = self._air_viscosity(T_avg)
        cp = self._air_specific_heat(T_avg)
        k = self._air_thermal_conductivity(T_avg)
        rho = self._air_density(T_avg)
        Pr = mu * cp / k
        return max(0.1, Pr)

    def calculate_grashof(self, T_flue: float, T_ambient: float = 25.0) -> float:
        T_avg = (T_flue + T_ambient) / 2
        beta = 1.0 / (T_avg + 273.15)
        delta_T = abs(T_flue - T_ambient)
        nu = self._air_viscosity(T_avg) / self._air_density(T_avg)
        Gr = self.g * beta * delta_T * (self.params.flue_length ** 3) / (nu ** 2)
        return max(1.0, Gr)

    def calculate_rayleigh(self, Gr: float, Pr: float) -> float:
        return Gr * Pr

    def _laminar_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        L_over_D = self.params.flue_length / self.params.flue_diameter
        Ra = self.calculate_rayleigh(Gr, Pr)

        if Ra < 1e9:
            Nu_natural = 0.59 * Ra ** 0.25
        else:
            Nu_natural = 0.10 * Ra ** (1.0 / 3.0)

        if Re < 2300:
            Nu_forced = 3.66 + (0.0668 * (self.params.flue_diameter / self.params.flue_length) * Re * Pr) / \
                        (1 + 0.04 * ((self.params.flue_diameter / self.params.flue_length) * Re * Pr) ** (2.0 / 3.0))
        else:
            Nu_forced = 0.023 * Re ** 0.8 * Pr ** 0.4

        Nu = (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)
        return max(1.0, Nu)

    def _transitional_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        Nu_laminar = self._laminar_nusselt(Re, Pr, Gr)
        Re_c = 2300
        Re_t = 4000
        w = (Re - Re_c) / (Re_t - Re_c)
        Nu_turbulent = 0.023 * Re ** 0.8 * Pr ** 0.4
        return (1 - w) * Nu_laminar + w * Nu_turbulent

    def _turbulent_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        Ra = self.calculate_rayleigh(Gr, Pr)
        if Ra < 1e9:
            Nu_natural = 0.59 * Ra ** 0.25
        else:
            Nu_natural = 0.10 * Ra ** (1.0 / 3.0)
        Nu_forced = 0.023 * Re ** 0.8 * Pr ** 0.4
        return (Nu_natural ** 3 + Nu_forced ** 3) ** (1.0 / 3.0)

    def calculate_nusselt(self, Re: float, Pr: float, Gr: float) -> float:
        if Re < 2300:
            return self._laminar_nusselt(Re, Pr, Gr)
        elif Re < 4000:
            return self._transitional_nusselt(Re, Pr, Gr)
        else:
            return self._turbulent_nusselt(Re, Pr, Gr)

    def calculate_flow_regime(self, Re: float) -> str:
        if Re < 2300:
            return "laminar"
        elif Re < 4000:
            return "transitional"
        else:
            return "turbulent"

    def calculate_heat_transfer_coefficient(self, Nu: float, T_flue: float, T_ambient: float = 25.0) -> float:
        T_avg = (T_flue + T_ambient) / 2
        k = self._air_thermal_conductivity(T_avg)
        return Nu * k / self.params.flue_diameter

    def calculate_pressure_drop(self, velocity: float, T_flue: float, T_ambient: float = 25.0, Re: Optional[float] = None) -> float:
        if Re is None:
            Re = self.calculate_reynolds(velocity, T_flue, T_ambient)
        T_avg = (T_flue + T_ambient) / 2
        rho = self._air_density(T_avg)

        if Re < 2300:
            f = 64.0 / Re
        elif Re < 4000:
            f_lam = 64.0 / 2300
            f_turb = 0.3164 * 4000 ** (-0.25)
            w = (Re - 2300) / (4000 - 2300)
            f = (1 - w) * f_lam + w * f_turb
        elif Re < 1e5:
            f = 0.3164 * Re ** (-0.25)
        else:
            f = 0.184 * Re ** (-0.2)

        delta_P = f * (self.params.flue_length / self.params.flue_diameter) * 0.5 * rho * velocity ** 2
        return max(0.0, delta_P)

    def calculate_outlet_temperature(
        self,
        T_inlet: float,
        T_ambient: float,
        velocity: float,
        h: Optional[float] = None,
        Re: Optional[float] = None,
        Pr: Optional[float] = None,
        Gr: Optional[float] = None
    ) -> float:
        if h is None:
            if Re is None:
                Re = self.calculate_reynolds(velocity, T_inlet, T_ambient)
            if Pr is None:
                Pr = self.calculate_prandtl(T_inlet, T_ambient)
            if Gr is None:
                Gr = self.calculate_grashof(T_inlet, T_ambient)
            Nu = self.calculate_nusselt(Re, Pr, Gr)
            h = self.calculate_heat_transfer_coefficient(Nu, T_inlet, T_ambient)

        T_avg = (T_inlet + T_ambient) / 2
        rho = self._air_density(T_avg)
        cp = self._air_specific_heat(T_avg)
        A = self.params.flue_cross_section_area
        m_dot = rho * velocity * A

        if m_dot <= 0:
            return T_inlet

        P_perimeter = math.pi * self.params.flue_diameter
        exponent = -(h * P_perimeter * self.params.flue_length) / (m_dot * cp)
        exponent = max(-10.0, min(0.0, exponent))

        T_outlet = T_ambient + (T_inlet - T_ambient) * math.exp(exponent)
        return T_outlet

    def calculate_settling_efficiency(
        self,
        T_inlet: float,
        T_outlet: float,
        velocity: float,
        residence_time: Optional[float] = None
    ) -> float:
        if residence_time is None:
            residence_time = self.params.flue_length / max(velocity, 0.01)

        cooling_ratio = (T_inlet - T_outlet) / max(T_inlet - 25.0, 1.0)
        cooling_ratio = max(0.0, min(1.0, cooling_ratio))

        d_particle = 2.5e-6
        rho_particle = 2000.0
        T_avg = (T_inlet + T_outlet) / 2
        mu = self._air_viscosity(T_avg)

        v_settling = (rho_particle * self.g * d_particle ** 2) / (18.0 * mu)

        flue_height = self.params.flue_length * 0.3
        settling_time = flue_height / max(v_settling, 1e-9)

        time_ratio = residence_time / max(settling_time, 1e-6)
        time_ratio = max(0.0, min(1.0, time_ratio))

        efficiency = 0.4 * cooling_ratio + 0.6 * time_ratio
        efficiency = efficiency * 100.0
        return max(0.0, min(95.0, efficiency))

    def simulate(
        self,
        flue_temperature: float,
        flue_velocity: float,
        ambient_temperature: float = 25.0,
        ambient_humidity: float = 50.0,
        oil_consumption: Optional[float] = None
    ) -> Dict:
        T_inlet = flue_temperature
        T_ambient = ambient_temperature

        Re = self.calculate_reynolds(flue_velocity, T_inlet, T_ambient)
        Pr = self.calculate_prandtl(T_inlet, T_ambient)
        Gr = self.calculate_grashof(T_inlet, T_ambient)
        Nu = self.calculate_nusselt(Re, Pr, Gr)
        h = self.calculate_heat_transfer_coefficient(Nu, T_inlet, T_ambient)
        delta_P = self.calculate_pressure_drop(flue_velocity, T_inlet, T_ambient, Re)
        T_outlet = self.calculate_outlet_temperature(T_inlet, T_ambient, flue_velocity, h, Re, Pr, Gr)
        flow_regime = self.calculate_flow_regime(Re)

        mass_flow_in = self._air_density(T_inlet) * flue_velocity * self.params.flue_cross_section_area
        mass_flow_out = self._air_density(T_outlet) * flue_velocity * self.params.flue_cross_section_area
        outlet_velocity = flue_velocity * (mass_flow_in / max(mass_flow_out, 1e-9))

        settling_efficiency = self.calculate_settling_efficiency(T_inlet, T_outlet, flue_velocity)

        result = {
            "time": datetime.now(),
            "reynolds_number": round(Re, 2),
            "prandtl_number": round(Pr, 4),
            "nusselt_number": round(Nu, 4),
            "heat_transfer_coeff": round(h, 4),
            "pressure_drop": round(delta_P, 4),
            "settling_efficiency": round(settling_efficiency, 2),
            "outlet_temperature": round(T_outlet, 2),
            "outlet_velocity": round(outlet_velocity, 4),
            "flow_regime": flow_regime,
        }

        logger.debug(
            f"烟道仿真完成: Re={Re:.1f}, Pr={Pr:.3f}, Nu={Nu:.2f}, "
            f"h={h:.2f}W/m²·K, ΔP={delta_P:.2f}Pa, "
            f"T_out={T_outlet:.1f}°C, 沉降效率={settling_efficiency:.1f}%, 流型={flow_regime}"
        )

        return result

    def get_flow_path_points(self, num_points: int = 50) -> list:
        points = []
        for i in range(num_points):
            t = i / (num_points - 1)
            x = 0.0
            y = t * self.params.flue_length
            z = 0.0
            points.append((x, y, z))
        return points

    def get_particle_trajectory(
        self,
        start_pos: tuple,
        flue_velocity: float,
        T_inlet: float,
        T_ambient: float = 25.0,
        dt: float = 0.01,
        num_steps: int = 200
    ) -> list:
        trajectory = [start_pos]
        x, y, z = start_pos

        for _ in range(num_steps):
            T_local = T_inlet - (T_inlet - T_ambient) * (y / max(self.params.flue_length, 0.01))
            T_local = max(T_ambient, T_local)
            Re = self.calculate_reynolds(flue_velocity, T_local, T_ambient)
            T_avg = (T_local + T_ambient) / 2
            rho = self._air_density(T_avg)
            mu = self._air_viscosity(T_avg)

            d_particle = 2.5e-6
            rho_particle = 2000.0
            v_rel_x = 0
            v_rel_y = flue_velocity - 0
            v_rel_z = 0
            drag_coeff = 6.0 * math.pi * mu * (d_particle / 2.0)
            F_drag_x = drag_coeff * v_rel_x
            F_drag_y = drag_coeff * v_rel_y
            F_drag_z = drag_coeff * v_rel_z
            F_buoyancy = (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3 * (rho - rho_particle) * self.g

            mass_particle = (4.0 / 3.0) * math.pi * (d_particle / 2.0) ** 3 * rho_particle
            ax = F_drag_x / max(mass_particle, 1e-20)
            ay = (F_drag_y + F_buoyancy) / max(mass_particle, 1e-20)
            az = F_drag_z / max(mass_particle, 1e-20)

            vx = 0 + ax * dt
            vy = flue_velocity * 0.8 + ay * dt
            vz = 0 + az * dt

            x += vx * dt
            y += vy * dt
            z += vz * dt

            r_max = self.params.flue_diameter / 2
            r = math.sqrt(x ** 2 + z ** 2)
            if r > r_max:
                scale = r_max / r
                x *= scale
                z *= scale

            if y >= self.params.flue_length:
                trajectory.append((x, self.params.flue_length, z))
                break

            trajectory.append((x, y, z))

        return trajectory
