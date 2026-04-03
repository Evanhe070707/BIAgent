# BIAgent

**BIAgent** 是一个用于处理氢燃料电池汽车 1 秒采样 CSV 数据的指标计算工具。
它通过 YAML 定义指标（`config/metrics.yaml`），使用 DuckDB 执行 SQL，输出每文件及合并结果 CSV。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
python -m biagent.cli data1.csv [data2.csv ...] \
    [--metrics config/metrics.yaml] \
    [--stk-cell-count 400] \
    [--stk-h2-corr 0.985] \
    [--output-dir results]
```

- `--stk-cell-count`：电堆片数（整数），不提供时程序会提示输入。
- `--stk-h2-corr`：氢气修正系数，默认 0.985。
- `--output-dir`：结果输出目录，默认 `results/`。

每个输入文件生成 `<stem>_result.csv`；多文件时额外输出 `combined_result.csv`。

## CSV 信号说明

| 信号 | 说明 |
|------|------|
| VehSpd | 车速 (km/h) |
| BattCurr / BattVolt | 动力电池电流/电压 |
| MotCurr / MotVolt | 驱动电机电流/电压 |
| StkCurr / StkVolt | 电堆电流/电压 |
| DcfCurrOut / DcfVoltOut | DC/DC 输出电流/电压 |
| WcpCurr / WcpVolt | 空压机电流/电压 |
| HrbCurr / HrbVolt | 氢气循环泵电流/电压 |
| AcpCurr / AcpVolt | 冷却泵电流/电压 |

列名匹配大小写不敏感。

## 运行测试

```bash
pytest tests/ -v
```

## 指标列表

详见 `config/metrics.yaml`。主要指标包括：

- 时间/里程：`TimeReady`, `TimeDrv`, `TimeStop`, `TimeFC`, `TotalDist`, `SysOpr_Dist`
- 能量 (kWh)：`StkEng_all`, `FCEng_all`, `BattEng_all`, `DrvEng_all`, `VehEng_all`, `AuxEng_all` 等
- 氢耗 (kg)：`H2_all_long`, `H2EleRatio`, `H_all_Long`, `VehH_Dist`
- 效率 (%)：`StkEff`, `FcSysEff`
- 百公里能耗 (kWh/100km)：`DrvEng_Dist`, `FCEng_Dist`, `AuxEng_Dist` 等
- 百公里氢耗 (kg/100km)：`DrvH2_Dist`, `FcBopH2_Dist` 等
- 平均功率 (kW)：`VehEng_T`, `DrvEng_T`, `FCEng_T`, `BattEng_T`, `AuxEng_T`
- 行车平均功率 (kW)：`VehEng_DrvT`, `DrvEng_DrvT`, `DrvEng_Pos_DrvT`, `DrvEng_Neg_DrvT`
