from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, insert
from datetime import datetime, timedelta
from typing import Optional, List
import logging

from ..database import get_db
from ..models.lamp import SensorData, FlueSimulation, AirQualityAnalysis, PM25Grid, Lamp
from ..schemas.sensor import (
    SensorDataCreate,
    SensorDataResponse,
    FlueSimulationResponse,
    AirQualityResponse,
    PM25GridResponse,
    PM25GridPoint,
    CombinedDataResponse,
    AlertResponse,
    StatisticsResponse,
    LampResponse
)
from ..services.flue_simulation import FlueFluidSimulator, FUEL_TYPES
from ..services.air_quality import AirQualityAnalyzer
from ..services.alert_service import alert_service
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sensor"])

flue_simulator = FlueFluidSimulator()
air_quality_analyzer = AirQualityAnalyzer(
    room_size_x=settings.ROOM_SIZE_X,
    room_size_y=settings.ROOM_SIZE_Y,
    room_size_z=settings.ROOM_SIZE_Z,
    grid_resolution=settings.GRID_RESOLUTION,
    air_change_rate=settings.AIR_CHANGE_RATE,
    outdoor_pm25=settings.OUTDOOR_PM25,
    inlet_position=settings.VENTILATION_INLET,
    outlet_position=settings.VENTILATION_OUTLET
)


@router.get("/lamps", response_model=List[LampResponse])
async def get_lamps(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Lamp).order_by(Lamp.lamp_id))
    return list(result.scalars().all())


@router.post("/sensor/data")
async def ingest_sensor_data(
    data: SensorDataCreate,
    db: AsyncSession = Depends(get_db)
):
    now = datetime.now()

    sensor_stmt = insert(SensorData).values(
        time=now,
        lamp_id=data.lamp_id,
        oil_consumption=data.oil_consumption,
        flue_temperature=data.flue_temperature,
        flue_velocity=data.flue_velocity,
        indoor_pm25=data.indoor_pm25,
        oil_level=data.oil_level,
        ambient_temperature=data.ambient_temperature,
        ambient_humidity=data.ambient_humidity
    )
    await db.execute(sensor_stmt)

    ambient_temp = data.ambient_temperature or 25.0
    ambient_hum = data.ambient_humidity or 50.0

    fuel_type = data.fuel_type or settings.DEFAULT_FUEL_TYPE
    air_change_rate = data.air_change_rate if data.air_change_rate is not None else settings.AIR_CHANGE_RATE
    outdoor_pm25 = data.outdoor_pm25 if data.outdoor_pm25 is not None else settings.OUTDOOR_PM25

    flue_result = flue_simulator.simulate(
        flue_temperature=data.flue_temperature,
        flue_velocity=data.flue_velocity,
        ambient_temperature=ambient_temp,
        ambient_humidity=ambient_hum,
        oil_consumption=data.oil_consumption,
        fuel_type=fuel_type
    )

    flue_stmt = insert(FlueSimulation).values(
        time=now,
        lamp_id=data.lamp_id,
        reynolds_number=flue_result["reynolds_number"],
        prandtl_number=flue_result["prandtl_number"],
        nusselt_number=flue_result["nusselt_number"],
        heat_transfer_coeff=flue_result["heat_transfer_coeff"],
        pressure_drop=flue_result["pressure_drop"],
        settling_efficiency=flue_result["settling_efficiency"],
        outlet_temperature=flue_result["outlet_temperature"],
        outlet_velocity=flue_result["outlet_velocity"],
        flow_regime=flue_result["flow_regime"]
    )
    await db.execute(flue_stmt)

    air_quality_result, grid_data = air_quality_analyzer.analyze(
        indoor_pm25=data.indoor_pm25,
        flue_temperature=data.flue_temperature,
        flue_velocity=data.flue_velocity,
        settling_efficiency=flue_result["settling_efficiency"],
        ambient_temperature=ambient_temp,
        ambient_humidity=ambient_hum,
        oil_consumption=data.oil_consumption,
        air_change_rate=air_change_rate,
        outdoor_pm25=outdoor_pm25
    )

    aq_stmt = insert(AirQualityAnalysis).values(
        time=now,
        lamp_id=data.lamp_id,
        pm25_diffusion_coeff=air_quality_result["pm25_diffusion_coeff"],
        pm25_gradient_x=air_quality_result["pm25_gradient_x"],
        pm25_gradient_y=air_quality_result["pm25_gradient_y"],
        pm25_gradient_z=air_quality_result["pm25_gradient_z"],
        purification_rate=air_quality_result["purification_rate"],
        air_change_efficiency=air_quality_result["air_change_efficiency"],
        aqi_level=air_quality_result["aqi_level"],
        health_risk=air_quality_result["health_risk"]
    )
    await db.execute(aq_stmt)

    for point in grid_data:
        grid_stmt = insert(PM25Grid).values(
            time=now,
            lamp_id=data.lamp_id,
            grid_x=point["grid_x"],
            grid_y=point["grid_y"],
            grid_z=point["grid_z"],
            concentration=point["concentration"]
        )
        await db.execute(grid_stmt)

    alerts = await alert_service.check_and_create_alerts(
        db=db,
        lamp_id=data.lamp_id,
        flue_velocity=data.flue_velocity,
        flue_temperature=data.flue_temperature,
        indoor_pm25=data.indoor_pm25
    )

    alert_service.publish_sensor_data({
        "time": now.isoformat(),
        "lamp_id": data.lamp_id,
        "oil_consumption": data.oil_consumption,
        "flue_temperature": data.flue_temperature,
        "flue_velocity": data.flue_velocity,
        "indoor_pm25": data.indoor_pm25,
        "settling_efficiency": flue_result["settling_efficiency"],
        "aqi_level": air_quality_result["aqi_level"]
    })

    await db.commit()

    return {
        "status": "success",
        "time": now.isoformat(),
        "flue_simulation": flue_result,
        "air_quality": air_quality_result,
        "alerts": alerts
    }


@router.get("/sensor/data/latest", response_model=CombinedDataResponse)
async def get_latest_data(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    sensor_query = select(SensorData).where(
        SensorData.lamp_id == lamp_id
    ).order_by(SensorData.time.desc()).limit(1)
    sensor_result = await db.execute(sensor_query)
    sensor_data = sensor_result.scalar_one_or_none()

    if not sensor_data:
        raise HTTPException(status_code=404, detail="未找到传感器数据")

    flue_query = select(FlueSimulation).where(
        FlueSimulation.lamp_id == lamp_id
    ).order_by(FlueSimulation.time.desc()).limit(1)
    flue_result = await db.execute(flue_query)
    flue_data = flue_result.scalar_one_or_none()

    aq_query = select(AirQualityAnalysis).where(
        AirQualityAnalysis.lamp_id == lamp_id
    ).order_by(AirQualityAnalysis.time.desc()).limit(1)
    aq_result = await db.execute(aq_query)
    aq_data = aq_result.scalar_one_or_none()

    active_alerts = await alert_service.get_active_alerts(db, lamp_id)

    return CombinedDataResponse(
        sensor=sensor_data,
        flue_simulation=flue_data,
        air_quality=aq_data,
        alerts=active_alerts
    )


@router.get("/sensor/data/history", response_model=List[SensorDataResponse])
async def get_sensor_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = select(SensorData).where(
        and_(
            SensorData.lamp_id == lamp_id,
            SensorData.time >= start_time
        )
    ).order_by(SensorData.time.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/flue/latest", response_model=Optional[FlueSimulationResponse])
async def get_latest_flue_simulation(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    query = select(FlueSimulation).where(
        FlueSimulation.lamp_id == lamp_id
    ).order_by(FlueSimulation.time.desc()).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("/simulation/flue/history", response_model=List[FlueSimulationResponse])
async def get_flue_simulation_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = select(FlueSimulation).where(
        and_(
            FlueSimulation.lamp_id == lamp_id,
            FlueSimulation.time >= start_time
        )
    ).order_by(FlueSimulation.time.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/air-quality/latest", response_model=Optional[AirQualityResponse])
async def get_latest_air_quality(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    query = select(AirQualityAnalysis).where(
        AirQualityAnalysis.lamp_id == lamp_id
    ).order_by(AirQualityAnalysis.time.desc()).limit(1)
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("/simulation/air-quality/history", response_model=List[AirQualityResponse])
async def get_air_quality_history(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    start_time = datetime.now() - timedelta(hours=hours)
    query = select(AirQualityAnalysis).where(
        and_(
            AirQualityAnalysis.lamp_id == lamp_id,
            AirQualityAnalysis.time >= start_time
        )
    ).order_by(AirQualityAnalysis.time.asc())

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/simulation/pm25-grid/latest", response_model=PM25GridResponse)
async def get_latest_pm25_grid(
    lamp_id: int = 1,
    db: AsyncSession = Depends(get_db)
):
    time_query = select(func.max(PM25Grid.time)).where(PM25Grid.lamp_id == lamp_id)
    time_result = await db.execute(time_query)
    latest_time = time_result.scalar_one_or_none()

    if not latest_time:
        raise HTTPException(status_code=404, detail="未找到PM2.5网格数据")

    query = select(PM25Grid).where(
        and_(
            PM25Grid.lamp_id == lamp_id,
            PM25Grid.time == latest_time
        )
    )
    result = await db.execute(query)
    grid_points = list(result.scalars().all())

    return PM25GridResponse(
        time=latest_time,
        lamp_id=lamp_id,
        grid_data=[
            PM25GridPoint(
                grid_x=p.grid_x,
                grid_y=p.grid_y,
                grid_z=p.grid_z,
                concentration=p.concentration
            ) for p in grid_points
        ]
    )


@router.get("/simulation/fuel-types")
async def get_fuel_types():
    """获取支持的燃料类型列表"""
    result = []
    for key, props in FUEL_TYPES.items():
        result.append({
            "fuel_type": key,
            "name": props["name"],
            "heating_value_mjkg": props["heating_value"],
            "modbus_value": props["modbus_value"]
        })
    return {"fuel_types": result}


@router.get("/simulation/particles")
async def get_particle_trajectories(
    flue_velocity: float = Query(0.5, ge=0.01, le=5.0),
    flue_temperature: float = Query(120.0, ge=20, le=300),
    num_particles: int = Query(20, ge=1, le=100),
    fuel_type: Optional[str] = Query(None, description="燃料类型")
):
    trajectories = []
    import random

    if fuel_type and fuel_type in FUEL_TYPES:
        flue_simulator.set_fuel_type(fuel_type)

    for i in range(num_particles):
        start_x = random.uniform(-0.02, 0.02)
        start_z = random.uniform(-0.02, 0.02)
        start_y = 0.0

        trajectory = flue_simulator.get_particle_trajectory(
            start_pos=(start_x, start_y, start_z),
            flue_velocity=flue_velocity,
            T_inlet=flue_temperature,
            T_ambient=25.0,
            dt=0.005,
            num_steps=300,
            fuel_type=fuel_type
        )
        trajectories.append({
            "particle_id": i,
            "points": [(round(p[0], 5), round(p[1], 5), round(p[2], 5)) for p in trajectory]
        })

    return {
        "flue_length": flue_simulator.params.flue_length,
        "flue_diameter": flue_simulator.params.flue_diameter,
        "fuel_type": fuel_type or flue_simulator.current_fuel_type,
        "fuel_name": FUEL_TYPES[fuel_type or flue_simulator.current_fuel_type]["name"],
        "trajectories": trajectories
    }


@router.get("/alerts/active", response_model=List[AlertResponse])
async def get_active_alerts(
    lamp_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    return await alert_service.get_active_alerts(db, lamp_id)


@router.get("/alerts/history", response_model=List[AlertResponse])
async def get_alert_history(
    lamp_id: Optional[int] = None,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    start_time = datetime.now() - timedelta(hours=hours)
    return await alert_service.get_alert_history(db, lamp_id, start_time)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db)
):
    success = await alert_service.resolve_alert(db, alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="告警不存在")
    return {"status": "success", "alert_id": alert_id}


@router.get("/statistics", response_model=StatisticsResponse)
async def get_statistics(
    lamp_id: int = 1,
    hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db)
):
    start_time = datetime.now() - timedelta(hours=hours)

    query = select(
        func.avg(SensorData.oil_consumption),
        func.avg(SensorData.flue_temperature),
        func.avg(SensorData.flue_velocity),
        func.avg(SensorData.indoor_pm25),
        func.max(SensorData.indoor_pm25),
        func.min(SensorData.indoor_pm25),
        func.count(SensorData.time)
    ).where(
        and_(
            SensorData.lamp_id == lamp_id,
            SensorData.time >= start_time
        )
    )

    result = await db.execute(query)
    row = result.one()

    return StatisticsResponse(
        lamp_id=lamp_id,
        start_time=start_time,
        end_time=datetime.now(),
        avg_oil_consumption=round(float(row[0] or 0), 3),
        avg_flue_temperature=round(float(row[1] or 0), 2),
        avg_flue_velocity=round(float(row[2] or 0), 3),
        avg_pm25=round(float(row[3] or 0), 2),
        max_pm25=round(float(row[4] or 0), 2),
        min_pm25=round(float(row[5] or 0), 2),
        data_points=int(row[6] or 0)
    )
