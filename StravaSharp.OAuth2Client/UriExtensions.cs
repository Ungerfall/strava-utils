namespace StravaSharp.OAuth2Client
{
    public static class UriExtensions
    {
        //
        // Summary:
        //     Replacement for HttpUtility.ParseQueryString
        //
        // Parameters:
        //   input:
        public static IDictionary<string, string> ParseQueryString(this string input)
        {
            // remove the leading ? if it's there
            if (input.StartsWith("?"))
            {
                input = input.Substring(1);
            }

            return input.Split('&')
                .Select(static keyValuePairs =>
                {
                    string[] keyAndValue = keyValuePairs.Split('=');
                    return new KeyValuePair<string, string>(keyAndValue[0], keyAndValue[1]);
                })
                .ToDictionary(static x => x.Key, static x => x.Value);
        }
    }
}
