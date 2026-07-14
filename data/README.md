# 数据工件 Data Artifacts

<!-- 自动生成文件，无需人工填写或编辑。 -->

## 黄金集 Golden

<table>
  <thead>
    <tr>
      <th>语言</th>
      <th>文档 ID</th>
      <th>Schema 版本</th>
      <th>Golden 版本</th>
      <th>状态</th>
      <th>文件</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>zh</td>
      <td>apt28_001</td>
      <td rowspan="6">1.0</td>
      <td rowspan="6">1.0</td>
      <td rowspan="6">current</td>
      <td><a href="golden/golden-zh-apt28_001-1.0-1.0.json">golden</a></td>
    </tr>
    <tr>
      <td>en</td>
      <td>apt28_080</td>
      <td><a href="golden/golden-en-apt28_080-1.0-1.0.json">golden</a></td>
    </tr>
    <tr>
      <td>zh</td>
      <td>kimsuky_001</td>
      <td><a href="golden/golden-zh-kimsuky_001-1.0-1.0.json">golden</a></td>
    </tr>
    <tr>
      <td>en</td>
      <td>kimsuky_060</td>
      <td><a href="golden/golden-en-kimsuky_060-1.0-1.0.json">golden</a></td>
    </tr>
    <tr>
      <td>zh</td>
      <td>lazarus_001</td>
      <td><a href="golden/golden-zh-lazarus_001-1.0-1.0.json">golden</a></td>
    </tr>
    <tr>
      <td>en</td>
      <td>lazarus_091</td>
      <td><a href="golden/golden-en-lazarus_091-1.0-1.0.json">golden</a></td>
    </tr>
  </tbody>
</table>

## 抽取结果 Extraction

<table>
  <thead>
    <tr>
      <th>文档 ID</th>
      <th>Schema 版本</th>
      <th>Prompt 版本</th>
      <th>模型</th>
      <th>运行时间</th>
      <th>状态</th>
      <th>文件</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>apt28_049</td>
      <td>1.0</td>
      <td>1.0</td>
      <td>manual-reviewed</td>
      <td>2026-07-09T12:10:32.840760+00:00</td>
      <td>legacy-migrated</td>
      <td><a href="extracted/extract-apt28_049-manual-reviewed-1.0-1.0-20260709121032840760.json">extract</a></td>
    </tr>
  </tbody>
</table>

## 评测结果 Evaluation

<table>
  <thead>
    <tr>
      <th>文档 ID</th>
      <th>Schema 版本</th>
      <th>Prompt 版本</th>
      <th>Golden 版本</th>
      <th>模型</th>
      <th>运行时间</th>
      <th>状态</th>
      <th>文件</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>apt28_080</td>
      <td>1.0</td>
      <td>extract-v1</td>
      <td></td>
      <td>deepseek-v4-flash</td>
      <td>2026-07-13T08:40:32.536611+00:00</td>
      <td>legacy</td>
      <td><a href="evaluation/evaluation_result.apt28_080.deepseek-v4-flash.extract-v1.json">evaluation</a></td>
    </tr>
  </tbody>
</table>
